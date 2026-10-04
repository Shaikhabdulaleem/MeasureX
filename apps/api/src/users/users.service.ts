import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { randomBytes } from 'crypto';
import * as argon2 from 'argon2';
import { Prisma, Role, User } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { canAccessBranch } from '../common/scope';
import { UserCreateDto, UserResetPasswordDto, UserUpdateDto } from './dto/user.dto';

/** Public user shape — never exposes the password hash (CLAUDE.md §14). */
export function serializeUser(u: User) {
  return {
    id: u.id,
    employeeId: u.employeeId,
    name: u.name,
    role: u.role,
    homeBranchId: u.homeBranchId,
    adminScope: (u.adminScope as string[] | null) ?? null,
    mustChangePassword: u.mustChangePassword,
    failedLogins: u.failedLogins,
    lockedUntil: u.lockedUntil?.toISOString() ?? null,
    status: u.status,
    createdAt: u.createdAt.toISOString(),
    updatedAt: u.updatedAt.toISOString(),
  };
}

/** A readable temporary password (Admin shares it; user must change on login). */
function generateTempPassword(): string {
  // 9 url-safe chars + a digit + symbol to satisfy any future policy.
  return `Mx-${randomBytes(6).toString('base64url')}1`;
}

@Injectable()
export class UsersService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /** GET /users — Admin, scoped to the admin's branches (home branch match). */
  async list(user: AuthUser, query: { branchId?: string; role?: Role; status?: string }) {
    const and: Prisma.UserWhereInput[] = [{ deletedAt: null }, this.scopeWhere(user)];
    if (query.branchId) and.push({ homeBranchId: query.branchId });
    if (query.role) and.push({ role: query.role });
    if (query.status === 'active' || query.status === 'inactive')
      and.push({ status: query.status });

    const users = await this.prisma.user.findMany({
      where: { AND: and },
      orderBy: [{ createdAt: 'desc' }],
    });
    return { items: users.map(serializeUser) };
  }

  async get(id: string, user: AuthUser) {
    return serializeUser(await this.findInScope(id, user));
  }

  async create(dto: UserCreateDto, actor: AuthUser, ip?: string) {
    if (!canAccessBranch(actor, dto.homeBranchId)) {
      throw new ConflictException({
        code: 'BRANCH_OUT_OF_SCOPE',
        message: 'Home branch is outside your admin scope',
      });
    }
    // Privilege-escalation guard: a scoped admin may only grant an admin scope
    // that is a subset of their own; only an "all" admin may grant "all".
    if (dto.role === Role.admin) {
      this.assertCanGrantScope(actor, dto.adminScope ?? []);
    }
    const branch = await this.prisma.branch.findFirst({
      where: { id: dto.homeBranchId, deletedAt: null },
    });
    if (!branch) {
      throw new BadRequestException({ code: 'BRANCH_NOT_FOUND', message: 'Home branch not found' });
    }
    const dup = await this.prisma.user.findUnique({ where: { employeeId: dto.employeeId } });
    if (dup) {
      throw new ConflictException({
        code: 'EMPLOYEE_ID_TAKEN',
        message: 'Employee id already exists',
      });
    }

    const tempPassword = dto.password ?? generateTempPassword();
    const passwordHash = await argon2.hash(tempPassword);

    const created = await this.prisma.user.create({
      data: {
        employeeId: dto.employeeId,
        name: dto.name,
        role: dto.role,
        homeBranchId: dto.homeBranchId,
        adminScope:
          dto.role === Role.admin ? (dto.adminScope as Prisma.InputJsonValue) : Prisma.JsonNull,
        passwordHash,
        mustChangePassword: true,
        status: 'active',
      },
    });

    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'user',
      entityId: created.id,
      action: 'user_created',
      after: serializeUser(created),
      ip,
    });

    // The temp password is returned ONCE (never stored in plaintext or audited).
    return { ...serializeUser(created), tempPassword };
  }

  async update(id: string, dto: UserUpdateDto, actor: AuthUser, ip?: string) {
    const before = await this.findInScope(id, actor);
    if (dto.homeBranchId && !canAccessBranch(actor, dto.homeBranchId)) {
      throw new ConflictException({
        code: 'BRANCH_OUT_OF_SCOPE',
        message: 'Home branch is outside your admin scope',
      });
    }

    // No one may change their OWN role or admin scope (self-escalation guard).
    if (id === actor.sub && (dto.role !== undefined || dto.adminScope !== undefined)) {
      throw new ForbiddenException({
        code: 'CANNOT_EDIT_SELF',
        message: 'You cannot change your own role or admin scope',
      });
    }

    // Same subset rule when the update leaves the user an admin (incl. promotion):
    // validate the resulting scope against the actor's own scope.
    const resultingRole = dto.role ?? before.role;
    if (resultingRole === Role.admin) {
      const resultingScope = dto.adminScope ?? (before.adminScope as string[] | null) ?? [];
      this.assertCanGrantScope(actor, resultingScope);
    }

    const updated = await this.prisma.user.update({
      where: { id },
      data: {
        ...(dto.name !== undefined ? { name: dto.name } : {}),
        ...(dto.role !== undefined ? { role: dto.role } : {}),
        ...(dto.homeBranchId !== undefined ? { homeBranchId: dto.homeBranchId } : {}),
        ...(dto.adminScope !== undefined
          ? { adminScope: dto.adminScope as Prisma.InputJsonValue }
          : {}),
        ...(dto.status !== undefined ? { status: dto.status } : {}),
      },
    });

    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'user',
      entityId: id,
      action: 'user_updated',
      before: serializeUser(before),
      after: serializeUser(updated),
      ip,
    });

    return serializeUser(updated);
  }

  /** POST /users/{id}/reset-password — new temp password, forces a change. */
  async resetPassword(id: string, dto: UserResetPasswordDto, actor: AuthUser, ip?: string) {
    await this.findInScope(id, actor);
    const tempPassword = dto.password ?? generateTempPassword();
    const passwordHash = await argon2.hash(tempPassword);

    await this.prisma.$transaction(async (tx) => {
      await tx.user.update({
        where: { id },
        data: {
          passwordHash,
          mustChangePassword: true,
          failedLogins: 0,
          lockedUntil: null,
        },
      });
      // Revoke any live refresh sessions so the old credential can't persist.
      await tx.session.updateMany({
        where: { userId: id, revokedAt: null },
        data: { revokedAt: new Date() },
      });
    });

    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'user',
      entityId: id,
      action: 'user_password_reset',
      ip,
    });

    return { id, tempPassword };
  }

  /** POST /users/{id}/unlock — clear the lockout counters (PRD §3). */
  async unlock(id: string, actor: AuthUser, ip?: string) {
    const before = await this.findInScope(id, actor);
    const updated = await this.prisma.user.update({
      where: { id },
      data: { failedLogins: 0, lockedUntil: null },
    });
    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'user',
      entityId: id,
      action: 'user_unlocked',
      before: { failedLogins: before.failedLogins, lockedUntil: before.lockedUntil },
      after: { failedLogins: 0, lockedUntil: null },
      ip,
    });
    return serializeUser(updated);
  }

  // --- internals -----------------------------------------------------------

  /**
   * Privilege-escalation guard for granting an admin scope (PRD §3, §14): an
   * actor may only grant a scope they themselves hold.
   *  - Only an actor with scope "all" may grant "all".
   *  - A scoped actor may grant only a NON-EMPTY subset of their own branch ids.
   * Throws 403 SCOPE_ESCALATION otherwise.
   */
  private assertCanGrantScope(actor: AuthUser, requested: string[]): void {
    const wantsAll = requested.includes('all');
    const actorAll =
      actor.adminScope === 'all' ||
      (Array.isArray(actor.adminScope) && actor.adminScope.includes('all'));

    if (actorAll) return; // an "all" admin may grant anything

    const own = Array.isArray(actor.adminScope) ? actor.adminScope : [];
    const ok = !wantsAll && requested.length > 0 && requested.every((b) => own.includes(b));
    if (!ok) {
      throw new ForbiddenException({
        code: 'SCOPE_ESCALATION',
        message: 'You may only grant an admin scope within your own scope',
      });
    }
  }

  private async findInScope(id: string, actor: AuthUser): Promise<User> {
    const user = await this.prisma.user.findFirst({
      where: { AND: [{ id, deletedAt: null }, this.scopeWhere(actor)] },
    });
    if (!user) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'User not found' });
    }
    return user;
  }

  /** Admins see users in branches within their scope (or all). */
  private scopeWhere(actor: AuthUser): Prisma.UserWhereInput {
    if (actor.adminScope === 'all') return {};
    const ids = Array.isArray(actor.adminScope) ? actor.adminScope : [];
    if (ids.includes('all')) return {};
    if (ids.length === 0) return { id: { in: [] } };
    return { homeBranchId: { in: ids } };
  }
}
