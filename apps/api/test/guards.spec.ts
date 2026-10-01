import { ExecutionContext, ForbiddenException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Role } from '@prisma/client';
import { RolesGuard } from '../src/auth/guards/roles.guard';
import { PasswordChangeGuard } from '../src/auth/guards/password-change.guard';
import { ROLES_KEY } from '../src/auth/decorators/roles.decorator';
import { IS_PUBLIC_KEY } from '../src/auth/decorators/public.decorator';
import { ALLOW_PENDING_PASSWORD_KEY } from '../src/auth/decorators/allow-password-change.decorator';

function contextWithUser(user: unknown): ExecutionContext {
  return {
    switchToHttp: () => ({ getRequest: () => ({ user }) }),
    getHandler: () => () => undefined,
    getClass: () => class {},
  } as unknown as ExecutionContext;
}

describe('RolesGuard', () => {
  it('allows a user whose role is in the required set', () => {
    const reflector = { getAllAndOverride: () => [Role.admin] } as unknown as Reflector;
    const guard = new RolesGuard(reflector);
    expect(guard.canActivate(contextWithUser({ role: Role.admin }))).toBe(true);
  });

  it('forbids a user whose role is not permitted', () => {
    const reflector = { getAllAndOverride: () => [Role.admin] } as unknown as Reflector;
    const guard = new RolesGuard(reflector);
    expect(() => guard.canActivate(contextWithUser({ role: Role.labour }))).toThrow(
      ForbiddenException,
    );
  });

  it('allows any authenticated user when no roles are required', () => {
    const reflector = { getAllAndOverride: () => undefined } as unknown as Reflector;
    const guard = new RolesGuard(reflector);
    expect(guard.canActivate(contextWithUser({ role: Role.labour }))).toBe(true);
  });

  it('reads metadata under the ROLES_KEY', () => {
    expect(ROLES_KEY).toBe('roles');
  });
});

describe('PasswordChangeGuard', () => {
  function reflectorFor(flags: Record<string, boolean>): Reflector {
    return {
      getAllAndOverride: (key: string) => flags[key],
    } as unknown as Reflector;
  }

  it('blocks a pending-change user on a normal route', () => {
    const guard = new PasswordChangeGuard(reflectorFor({}));
    expect(() => guard.canActivate(contextWithUser({ mustChangePassword: true }))).toThrow(
      ForbiddenException,
    );
  });

  it('allows a pending-change user on an allow-pending route', () => {
    const guard = new PasswordChangeGuard(reflectorFor({ [ALLOW_PENDING_PASSWORD_KEY]: true }));
    expect(guard.canActivate(contextWithUser({ mustChangePassword: true }))).toBe(true);
  });

  it('allows public routes through', () => {
    const guard = new PasswordChangeGuard(reflectorFor({ [IS_PUBLIC_KEY]: true }));
    expect(guard.canActivate(contextWithUser(undefined))).toBe(true);
  });

  it('allows a user who does not owe a change', () => {
    const guard = new PasswordChangeGuard(reflectorFor({}));
    expect(guard.canActivate(contextWithUser({ mustChangePassword: false }))).toBe(true);
  });
});
