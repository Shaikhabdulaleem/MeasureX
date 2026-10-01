import {
  BadRequestException,
  HttpException,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { Prisma, User } from '@prisma/client';
import * as argon2 from 'argon2';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { ChangePasswordDto, LoginDto } from './dto/auth.dto';

export const MAX_FAILED_LOGINS = 5;
export const LOCKOUT_MINUTES = 15;

/** HTTP 423 Locked — account temporarily locked after too many failures. */
export class AccountLockedException extends HttpException {
  constructor(lockedUntil: Date) {
    // HTTP 423 Locked (not present in Nest's HttpStatus enum).
    super({ code: 'ACCOUNT_LOCKED', message: 'Account locked', details: { lockedUntil } }, 423);
  }
}

export interface PublicUser {
  id: string;
  employeeId: string;
  name: string;
  role: string;
  homeBranchId: string;
  adminScope: Prisma.JsonValue | null;
  mustChangePassword: boolean;
  status: string;
}

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  accessTokenExpiresAt: string;
  refreshTokenExpiresAt: string;
  mustChangePassword: boolean;
  user: PublicUser;
}

@Injectable()
export class AuthService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly jwt: JwtService,
    private readonly audit: AuditService,
  ) {}

  async login(dto: LoginDto, ip?: string): Promise<TokenPair> {
    const employeeId = dto.employeeId.trim();
    const user = await this.prisma.user.findFirst({
      where: { employeeId, deletedAt: null },
    });

    if (!user || user.status !== 'active') {
      await this.audit.record({
        entity: 'auth',
        entityId: user?.id ?? null,
        action: 'login_failed',
        reason: user ? 'inactive_user' : 'unknown_user',
        ip,
      });
      throw new UnauthorizedException({
        code: 'INVALID_CREDENTIALS',
        message: 'Invalid credentials',
      });
    }

    if (user.lockedUntil && user.lockedUntil > new Date()) {
      await this.audit.record({
        entity: 'auth',
        entityId: user.id,
        role: user.role,
        action: 'login_locked',
        reason: 'account_locked',
        ip,
      });
      throw new AccountLockedException(user.lockedUntil);
    }

    const valid = await argon2.verify(user.passwordHash, dto.password);
    if (!valid) {
      await this.registerFailedLogin(user, ip);
      throw new UnauthorizedException({
        code: 'INVALID_CREDENTIALS',
        message: 'Invalid credentials',
      });
    }

    if (user.failedLogins !== 0 || user.lockedUntil) {
      await this.prisma.user.update({
        where: { id: user.id },
        data: { failedLogins: 0, lockedUntil: null },
      });
    }

    await this.audit.record({
      entity: 'auth',
      entityId: user.id,
      role: user.role,
      action: 'login_success',
      ip,
    });

    return this.issueTokens(user, dto.installId);
  }

  async refresh(refreshToken: string, ip?: string): Promise<TokenPair> {
    let payload: { sub: string; sid: string; type?: string };
    try {
      payload = this.jwt.verify(refreshToken, { secret: this.refreshSecret() });
    } catch {
      throw new UnauthorizedException({ code: 'INVALID_TOKEN', message: 'Invalid refresh token' });
    }
    if (payload.type !== 'refresh') {
      throw new UnauthorizedException({ code: 'INVALID_TOKEN', message: 'Invalid refresh token' });
    }

    const session = await this.prisma.session.findUnique({ where: { id: payload.sid } });
    if (
      !session ||
      session.revokedAt ||
      session.expiresAt < new Date() ||
      session.userId !== payload.sub ||
      !(await argon2.verify(session.refreshTokenHash, refreshToken))
    ) {
      throw new UnauthorizedException({ code: 'INVALID_TOKEN', message: 'Invalid refresh token' });
    }

    const user = await this.prisma.user.findFirst({
      where: { id: session.userId, deletedAt: null },
    });
    if (!user || user.status !== 'active') {
      throw new UnauthorizedException({ code: 'INVALID_TOKEN', message: 'Invalid refresh token' });
    }

    // Rotate: revoke the old session, issue a fresh pair.
    await this.prisma.session.update({
      where: { id: session.id },
      data: { revokedAt: new Date() },
    });
    await this.audit.record({
      entity: 'auth',
      entityId: user.id,
      role: user.role,
      action: 'token_refreshed',
      ip,
    });
    return this.issueTokens(user, session.installId ?? undefined);
  }

  async logout(
    userId: string,
    role: string,
    refreshToken: string | undefined,
    ip?: string,
  ): Promise<void> {
    if (refreshToken) {
      try {
        const payload = this.jwt.verify<{ sid: string }>(refreshToken, {
          secret: this.refreshSecret(),
        });
        await this.prisma.session.updateMany({
          where: { id: payload.sid, userId, revokedAt: null },
          data: { revokedAt: new Date() },
        });
      } catch {
        // Ignore an unparseable token; fall through to revoke-all below is not
        // applied so a bad token cannot nuke other sessions.
      }
    } else {
      await this.prisma.session.updateMany({
        where: { userId, revokedAt: null },
        data: { revokedAt: new Date() },
      });
    }

    await this.audit.record({
      entity: 'auth',
      entityId: userId,
      role: role as never,
      action: 'logout',
      ip,
    });
  }

  async changePassword(userId: string, dto: ChangePasswordDto, ip?: string): Promise<void> {
    const user = await this.prisma.user.findFirst({ where: { id: userId, deletedAt: null } });
    if (!user) {
      throw new UnauthorizedException({ code: 'INVALID_TOKEN', message: 'Unknown user' });
    }

    const valid = await argon2.verify(user.passwordHash, dto.currentPassword);
    if (!valid) {
      await this.audit.record({
        entity: 'auth',
        entityId: user.id,
        role: user.role,
        action: 'password_change_failed',
        reason: 'wrong_current_password',
        ip,
      });
      throw new BadRequestException({
        code: 'INVALID_CURRENT_PASSWORD',
        message: 'Current password is incorrect',
      });
    }

    const newHash = await argon2.hash(dto.newPassword);
    await this.prisma.user.update({
      where: { id: user.id },
      data: { passwordHash: newHash, mustChangePassword: false },
    });
    // Force re-authentication on other devices.
    await this.prisma.session.updateMany({
      where: { userId: user.id, revokedAt: null },
      data: { revokedAt: new Date() },
    });

    await this.audit.record({
      entity: 'auth',
      entityId: user.id,
      role: user.role,
      action: 'password_changed',
      ip,
    });
  }

  // --- internals -----------------------------------------------------------

  private async registerFailedLogin(user: User, ip?: string): Promise<void> {
    const failed = user.failedLogins + 1;
    const locked = failed >= MAX_FAILED_LOGINS;
    await this.prisma.user.update({
      where: { id: user.id },
      data: {
        failedLogins: failed,
        lockedUntil: locked ? new Date(Date.now() + LOCKOUT_MINUTES * 60_000) : user.lockedUntil,
      },
    });
    await this.audit.record({
      entity: 'auth',
      entityId: user.id,
      role: user.role,
      action: locked ? 'login_locked' : 'login_failed',
      reason: locked ? 'max_attempts_reached' : 'bad_password',
      after: { failedLogins: failed },
      ip,
    });
  }

  private async issueTokens(user: User, installId: string | undefined): Promise<TokenPair> {
    const now = Date.now();
    const accessTtlMs = parseDuration(process.env.JWT_ACCESS_TTL ?? '15m');
    const refreshTtlMs = parseDuration(process.env.JWT_REFRESH_TTL ?? '12h');

    const session = await this.prisma.session.create({
      data: {
        userId: user.id,
        refreshTokenHash: 'pending',
        expiresAt: new Date(now + refreshTtlMs),
        installId: installId ?? null,
      },
    });

    const accessToken = this.jwt.sign(
      {
        sub: user.id,
        employeeId: user.employeeId,
        role: user.role,
        homeBranchId: user.homeBranchId,
        adminScope: user.adminScope ?? null,
        mustChangePassword: user.mustChangePassword,
        type: 'access',
      },
      { secret: this.accessSecret(), expiresIn: Math.floor(accessTtlMs / 1000) },
    );
    const refreshToken = this.jwt.sign(
      { sub: user.id, sid: session.id, type: 'refresh' },
      { secret: this.refreshSecret(), expiresIn: Math.floor(refreshTtlMs / 1000) },
    );

    await this.prisma.session.update({
      where: { id: session.id },
      data: { refreshTokenHash: await argon2.hash(refreshToken) },
    });

    return {
      accessToken,
      refreshToken,
      accessTokenExpiresAt: new Date(now + accessTtlMs).toISOString(),
      refreshTokenExpiresAt: new Date(now + refreshTtlMs).toISOString(),
      mustChangePassword: user.mustChangePassword,
      user: toPublicUser(user),
    };
  }

  private accessSecret(): string {
    return process.env.JWT_ACCESS_SECRET ?? 'dev-access-secret-change-me';
  }

  private refreshSecret(): string {
    return process.env.JWT_REFRESH_SECRET ?? 'dev-refresh-secret-change-me';
  }
}

function toPublicUser(user: User): PublicUser {
  return {
    id: user.id,
    employeeId: user.employeeId,
    name: user.name,
    role: user.role,
    homeBranchId: user.homeBranchId,
    adminScope: user.adminScope,
    mustChangePassword: user.mustChangePassword,
    status: user.status,
  };
}

/** Parse a short duration like "15m", "12h", "7d", "30s" into milliseconds. */
export function parseDuration(value: string): number {
  const match = /^(\d+)\s*([smhd])$/.exec(value.trim());
  if (!match) {
    const asNumber = Number(value);
    if (Number.isFinite(asNumber)) return asNumber * 1000;
    throw new Error(`Invalid duration: ${value}`);
  }
  const amount = Number(match[1]);
  const unit = match[2];
  const multipliers: Record<string, number> = {
    s: 1000,
    m: 60_000,
    h: 3_600_000,
    d: 86_400_000,
  };
  return amount * multipliers[unit]!;
}
