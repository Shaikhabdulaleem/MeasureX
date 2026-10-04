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

// --- M4: generic JSON helper --------------------------------------------------

async function apiFetch<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...authHeaders(token) } as Record<string, string>;
  if (init.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...headers, ...(init.headers ?? {}) },
  });
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function qs(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) sp.set(k, v);
  const s = sp.toString();
  return s ? `?${s}` : '';
}

// --- M4: package actions ------------------------------------------------------

export interface CorrectionInput {
  lengthMm: number;
  widthMm: number;
  heightMm: number;
  actualWeightG?: number | null;
  weightSource?: 'scale' | 'manual' | 'none';
  weightReason?: string;
  reason: string;
}

export const correctPackage = (token: string, id: string, body: CorrectionInput) =>
  apiFetch<PackageRow>(token, `/packages/${id}/corrections`, {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const voidPackage = (token: string, id: string, reason: string) =>
  apiFetch<PackageRow>(token, `/packages/${id}/void`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });

export const reopenShipment = (token: string, awb: string, reason: string) =>
  apiFetch<Shipment>(token, `/shipments/${encodeURIComponent(awb)}/reopen`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });

export interface VersionRow {
  id: string;
  versionNo: number;
  lengthMm: number;
  widthMm: number;
  heightMm: number;
  actualWeightG: number | null;
  weightSource: string;
  method: string;
  confidence: string | null;
  billingLCm: number;
  billingWCm: number;
  billingHCm: number;
  cbm: number;
  volumetricG: number;
  chargeableG: number;
  createdBy: string | null;
  reason: string | null;
  createdAt: string;
}

export const getPackageVersions = (token: string, id: string) =>
  apiFetch<{ packageId: string; currentVersionId: string | null; items: VersionRow[] }>(
    token,
    `/packages/${id}/versions`,
  );

// --- M4: review (flags + remeasurements) -------------------------------------

export interface Flag {
  id: string;
  shipmentId: string | null;
  packageId: string | null;
  type: string;
  status: string;
  resolvedBy: string | null;
  note: string | null;
  createdAt: string;
  awb?: string | null;
}

export const listFlags = (
  token: string,
  filters: { status?: string; type?: string; awb?: string } = {},
) => apiFetch<{ items: Flag[]; nextCursor: string | null }>(token, `/flags${qs(filters)}`);

export const resolveFlag = (
  token: string,
  id: string,
  action: 'approve' | 'dismiss',
  note?: string,
) =>
  apiFetch<Flag>(token, `/flags/${id}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ action, note }),
  });

export interface RemeasureRequestRow {
  id: string;
  shipmentId: string;
  packageIds: string[];
  reason: string;
  note: string | null;
  status: string;
  requestedBy: string;
  doneBy: string | null;
  closedAt: string | null;
  createdAt: string;
  awb?: string | null;
}

export const listRemeasurements = (token: string, status?: string) =>
  apiFetch<{ items: RemeasureRequestRow[]; nextCursor: string | null }>(
    token,
    `/remeasurements${qs({ status })}`,
  );

export const createRemeasure = (
  token: string,
  body: { shipmentId: string; packageIds: string[]; reason: string; note?: string },
) =>
  apiFetch<RemeasureRequestRow>(token, `/remeasurements`, {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const cancelRemeasure = (token: string, id: string) =>
  apiFetch<RemeasureRequestRow>(token, `/remeasurements/${id}/cancel`, { method: 'POST' });

// --- M4: admin ----------------------------------------------------------------

export interface AdminUser {
  id: string;
  employeeId: string;
  name: string;
  role: 'labour' | 'team_leader' | 'admin';
  homeBranchId: string;
  adminScope: string[] | null;
  mustChangePassword: boolean;
  failedLogins: number;
  lockedUntil: string | null;
  status: string;
}

export const listUsers = (
  token: string,
  filters: { branchId?: string; role?: string; status?: string } = {},
) => apiFetch<{ items: AdminUser[] }>(token, `/users${qs(filters)}`);

export const createUser = (
  token: string,
  body: {
    employeeId: string;
    name: string;
    role: string;
    homeBranchId: string;
    adminScope?: string[];
  },
) =>
  apiFetch<AdminUser & { tempPassword: string }>(token, `/users`, {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const updateUser = (
  token: string,
  id: string,
  body: Partial<Pick<AdminUser, 'name' | 'role' | 'homeBranchId' | 'adminScope' | 'status'>>,
) => apiFetch<AdminUser>(token, `/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) });

export const resetUserPassword = (token: string, id: string) =>
  apiFetch<{ id: string; tempPassword: string }>(token, `/users/${id}/reset-password`, {
    method: 'POST',
    body: '{}',
  });

export const unlockUser = (token: string, id: string) =>
  apiFetch<AdminUser>(token, `/users/${id}/unlock`, { method: 'POST' });

export interface Branch {
  id: string;
  code: string;
  name: string;
  status: string;
}

export const listBranches = (token: string) => apiFetch<{ items: Branch[] }>(token, `/branches`);
export const createBranch = (token: string, body: { code: string; name: string }) =>
  apiFetch<Branch>(token, `/branches`, { method: 'POST', body: JSON.stringify(body) });
export const updateBranch = (token: string, id: string, body: { name?: string; status?: string }) =>
  apiFetch<Branch>(token, `/branches/${id}`, { method: 'PATCH', body: JSON.stringify(body) });

export interface Station {
  id: string;
  code: string;
  branchId: string;
  matSizeMm: number;
  markerSizeMm: number;
  scaleId: string | null;
}

export const listStations = (token: string, branchId?: string) =>
  apiFetch<{ items: Station[] }>(token, `/stations${qs({ branchId })}`);
export const createStation = (
  token: string,
  body: {
    code: string;
    branchId: string;
    matSizeMm: number;
    markerSizeMm: number;
    scaleId?: string;
  },
) => apiFetch<Station>(token, `/stations`, { method: 'POST', body: JSON.stringify(body) });
export const updateStation = (
  token: string,
  id: string,
  body: { matSizeMm?: number; markerSizeMm?: number; scaleId?: string | null },
) => apiFetch<Station>(token, `/stations/${id}`, { method: 'PATCH', body: JSON.stringify(body) });

export interface Device {
  id: string;
  installId: string;
  manufacturer: string | null;
  model: string | null;
  os: string | null;
  osVersion: string | null;
  tier: string;
  lastUserId: string | null;
  lastSeenAt: string | null;
  blocked: boolean;
}

export const listDevices = (token: string, filters: { blocked?: string; tier?: string } = {}) =>
  apiFetch<{ items: Device[] }>(token, `/devices${qs(filters)}`);
export const blockDevice = (token: string, id: string, blocked: boolean) =>
  apiFetch<Device>(token, `/devices/${id}/block`, {
    method: 'POST',
    body: JSON.stringify({ blocked }),
  });

export interface EffectiveConfig {
  awbRegex: string;
  volumetricDivisor: number;
  dimensionRounding: string;
  chargeableStepKg: number;
  weightRequired: boolean;
  mediumConfirmAllowed: boolean;
  minDimensionCm: number;
  maxDimensionCm: number;
  idleAutoCompleteMinutes: number;
  retention: { photoMonths: number; localPurgeDays: number };
}

export const getConfig = (token: string) => apiFetch<EffectiveConfig>(token, `/config`);
export const updateConfig = (token: string, body: Record<string, unknown>) =>
  apiFetch<EffectiveConfig>(token, `/config`, { method: 'PUT', body: JSON.stringify(body) });

// --- M4: dashboard + audit ----------------------------------------------------

export interface Kpis {
  from: string;
  to: string;
  shipments: number;
  packages: number;
  cbm: number;
  chargeableG: number;
  manualEntryRate: number;
  retakeRate: number;
  flagsOpen: number;
  remeasuresOpen: number;
}

export const getKpis = (token: string, dateFrom?: string, dateTo?: string) =>
  apiFetch<{ today: Kpis; range: Kpis }>(token, `/dashboard/kpis${qs({ dateFrom, dateTo })}`);

export interface AuditRow {
  id: string;
  at: string;
  userId: string | null;
  role: string | null;
  entity: string;
  entityId: string | null;
  action: string;
  before: unknown;
  after: unknown;
  reason: string | null;
}

export const listAudit = (
  token: string,
  filters: {
    entity?: string;
    entityId?: string;
    action?: string;
    dateFrom?: string;
    dateTo?: string;
  } = {},
) => apiFetch<{ items: AuditRow[]; nextCursor: string | null }>(token, `/audit${qs(filters)}`);

// --- M4: reports (binary download) -------------------------------------------

/** Fetch a report with the auth header and trigger a browser download. */
export async function downloadReport(
  token: string,
  type: string,
  format: 'xlsx' | 'csv',
  filters: { dateFrom?: string; dateTo?: string; branchId?: string } = {},
): Promise<void> {
  const res = await fetch(`${BASE}/reports/${type}${qs({ format, ...filters })}`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw await parseError(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${type}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
