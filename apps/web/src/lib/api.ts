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

// --- M1: shipments -------------------------------------------------------

export interface ShipmentTotals {
  pieces: number;
  cbm: number;
  actualG: number;
  volumetricG: number;
  chargeableG: number;
}

export interface MeasurementVersion {
  lengthMm: number;
  widthMm: number;
  heightMm: number;
  billingLCm: number;
  billingWCm: number;
  billingHCm: number;
  cbm: number;
  volumetricG: number;
  chargeableG: number;
  actualWeightG: number | null;
  method: string;
  confidence: string | null;
}

export interface PhotoRef {
  id: string;
  kind: string;
}

export interface PackageRow {
  id: string;
  packageNumber: number | null;
  status: string;
  measuredBy: string | null;
  confirmedAt: string | null;
  currentVersion: MeasurementVersion | null;
  photos: PhotoRef[];
}

export interface Shipment {
  id: string;
  awb: string;
  branchId: string | null;
  status: string;
  flags: string[];
  totals: ShipmentTotals;
  completedAt: string | null;
  createdAt: string;
}

export interface ShipmentDetail extends Shipment {
  packages: PackageRow[];
}

export interface ShipmentFilters {
  awb?: string;
  branchId?: string;
  dateFrom?: string;
  dateTo?: string;
  employeeId?: string;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function listShipments(
  token: string,
  filters: ShipmentFilters = {},
): Promise<{ items: Shipment[]; nextCursor: string | null }> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  params.set('limit', '100');
  const res = await fetch(`${BASE}/shipments?${params.toString()}`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

export async function getShipment(token: string, awb: string): Promise<ShipmentDetail> {
  const res = await fetch(`${BASE}/shipments/${encodeURIComponent(awb)}`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

/** Signed, short-lived view URL for a photo (Team Leader / Admin only). */
export async function getPhotoUrl(token: string, photoId: string): Promise<string> {
  const res = await fetch(`${BASE}/photos/${photoId}`, { headers: authHeaders(token) });
  if (!res.ok) throw await parseError(res);
  const body = await res.json();
  return body.url as string;
}
