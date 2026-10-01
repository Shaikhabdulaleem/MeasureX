export interface PublicUser {
  id: string;
  employeeId: string;
  name: string;
  role: 'labour' | 'team_leader' | 'admin';
  homeBranchId: string;
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

export interface ApiError {
  status: number;
  code: string;
  message: string;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:3000/api/v1';

async function parseError(res: Response): Promise<ApiError> {
  let code = 'ERROR';
  let message = res.statusText;
  try {
    const body = await res.json();
    code = body.code ?? code;
    message = body.message ?? message;
  } catch {
    // non-JSON error body; keep defaults
  }
  return { status: res.status, code, message };
}

export async function login(employeeId: string, password: string): Promise<TokenPair> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employeeId, password }),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function changePassword(
  accessToken: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const res = await fetch(`${BASE}/auth/change-password`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ currentPassword, newPassword }),
  });
  if (!res.ok) throw await parseError(res);
}

export async function logout(accessToken: string, refreshToken: string): Promise<void> {
  await fetch(`${BASE}/auth/logout`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ refreshToken }),
  }).catch(() => undefined);
}
