import { SetMetadata } from '@nestjs/common';

export const ALLOW_PENDING_PASSWORD_KEY = 'allowPendingPassword';

/**
 * Marks a route reachable while the user still has must_change_password set
 * (change-password and logout). Every other route is blocked until the forced
 * change is done — see PasswordChangeGuard.
 */
export const AllowPendingPasswordChange = () => SetMetadata(ALLOW_PENDING_PASSWORD_KEY, true);
