import { createParamDecorator, ExecutionContext } from '@nestjs/common';

export interface AuthUser {
  sub: string;
  employeeId: string;
  role: string;
  homeBranchId: string;
  /** Admin scope: array of branch ids, the string "all", or null for non-admins. */
  adminScope: string[] | 'all' | null;
  mustChangePassword: boolean;
}

/** Injects the authenticated user (JWT payload) attached by JwtAuthGuard. */
export const CurrentUser = createParamDecorator(
  (_data: unknown, ctx: ExecutionContext): AuthUser => {
    const request = ctx.switchToHttp().getRequest<{ user: AuthUser }>();
    return request.user;
  },
);
