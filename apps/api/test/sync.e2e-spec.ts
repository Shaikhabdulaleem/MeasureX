import { INestApplication } from '@nestjs/common';
import { randomUUID } from 'crypto';
import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import {
  buildApp,
  createAndLogin,
  createBranch,
  randomAwb,
  uniqueEmployeeId,
  AuthContext,
} from './helpers';

const prisma = new PrismaClient();
let app: INestApplication;
let server: ReturnType<INestApplication['getHttpServer']>;
let labour: AuthContext;
let deviceA: string;
let deviceB: string;

const WORKED = { lengthMm: 452, widthMm: 301, heightMm: 204 };

interface ResultRow {
  id: string;
  status: string;
  packageNumber: number | null;
  error?: { code: string; message: string };
}
interface PackageRow {
  id: string;
  packageNumber: number | null;
}

/** A sync-batch item (PackageCreate + awb). */
function item(awb: string, extra: Record<string, unknown> = {}) {
  return {
    id: randomUUID(),
    awb,
    ...WORKED,
    method: 'manual',
    weightSource: 'none',
    confirmedAt: new Date().toISOString(),
    ...extra,
  };
}

function syncBatch(packages: Array<Record<string, unknown>>) {
  return request(server)
    .post('/api/v1/sync/batch')
    .set('Authorization', `Bearer ${labour.accessToken}`)
    .send({ packages });
}

/** Online single-create (append path), for the "two phones online" case. */
function createPackage(awb: string, body: Record<string, unknown>) {
  return request(server)
    .post(`/api/v1/shipments/${awb}/packages`)
    .set('Authorization', `Bearer ${labour.accessToken}`)
    .set('Idempotency-Key', randomUUID())
    .send(body);
}

async function createDevice(): Promise<string> {
  const id = randomUUID();
  await prisma.device.create({
    data: { id, installId: `install_${id}`, tier: 'standard' },
  });
  return id;
}

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  await prisma.config.upsert({
    where: { key: 'actual_weight_required' },
    update: { value: false },
    create: { key: 'actual_weight_required', value: false, scope: 'global' },
  });
  const branchId = await createBranch(prisma, 'SYN');
  labour = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('SYN_LAB'),
    role: 'labour',
  });
  deviceA = await createDevice();
  deviceB = await createDevice();
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

describe('POST /sync/batch — partial success', () => {
  it('stores the good items and fails only the bad one', async () => {
    const awb = randomAwb();
    const good1 = item(awb);
    const bad = item(awb, { lengthMm: 5 }); // 0.5 cm < 1 cm → DIMENSION_OUT_OF_RANGE
    const good2 = item(awb);

    const res = await syncBatch([good1, bad, good2]).expect(200);
    const results: ResultRow[] = res.body.results;

    const byId: Record<string, ResultRow> = Object.fromEntries(results.map((r) => [r.id, r]));
    expect(byId[good1.id].status).toBe('synced');
    expect(byId[good2.id].status).toBe('synced');
    expect(byId[bad.id].status).toBe('failed');
    expect(byId[bad.id].error?.code).toBe('DIMENSION_OUT_OF_RANGE');

    // Totals reflect only the two stored packages.
    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(detail.body.totals.pieces).toBe(2);
    expect(detail.body.packages).toHaveLength(2);
  });
});

describe('POST /sync/batch — idempotent replay', () => {
  it('a replayed batch creates no duplicates and keeps the same numbers', async () => {
    const awb = randomAwb();
    const batch = [item(awb), item(awb)];

    const first = await syncBatch(batch).expect(200);
    const firstNums = (first.body.results as ResultRow[])
      .map((r) => r.packageNumber as number)
      .sort((a, b) => a - b);
    expect(firstNums).toEqual([1, 2]);

    const replay = await syncBatch(batch).expect(200);
    for (const r of replay.body.results as ResultRow[]) expect(r.status).toBe('synced');
    const replayNums = (replay.body.results as ResultRow[])
      .map((r) => r.packageNumber as number)
      .sort((a, b) => a - b);
    expect(replayNums).toEqual([1, 2]);

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(detail.body.packages).toHaveLength(2);
  });
});

describe('POST /sync/batch — confirmed_at renumbering', () => {
  it('renumbers an already-assigned package when an earlier one syncs later', async () => {
    const awb = randomAwb();
    const tLater = new Date('2026-10-03T10:05:00.000Z').toISOString();
    const tEarlier = new Date('2026-10-03T10:00:00.000Z').toISOString();

    // Package A confirmed later, synced first → PKG 01 for now.
    const a = item(awb, { confirmedAt: tLater });
    const first = await syncBatch([a]).expect(200);
    expect(first.body.results[0].packageNumber).toBe(1);

    // Package B confirmed earlier, synced later → B must become PKG 01, A → PKG 02.
    const b = item(awb, { confirmedAt: tEarlier });
    const second = await syncBatch([b]).expect(200);
    expect(second.body.results[0].packageNumber).toBe(1);

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    const nums: Record<string, number | null> = Object.fromEntries(
      (detail.body.packages as PackageRow[]).map((p) => [p.id, p.packageNumber]),
    );
    expect(nums[b.id]).toBe(1);
    expect(nums[a.id]).toBe(2);
  });
});

describe('POST /sync/batch — possible duplicate across devices', () => {
  it('flags two devices that measured the same AWB while offline', async () => {
    // Both confirmed in the past (offline), then synced now: each item is
    // received after the other was confirmed → concurrent offline capture.
    const awb = randomAwb();
    const past = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    const a = item(awb, { deviceId: deviceA, confirmedAt: past });
    const b = item(awb, { deviceId: deviceB, confirmedAt: past });

    const res = await syncBatch([a, b]).expect(200);
    const statuses = (res.body.results as ResultRow[]).map((r) => r.status);
    expect(statuses).toContain('conflict'); // the second device triggers the flag

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(detail.body.packages).toHaveLength(2);
    expect(detail.body.flags).toContain('possible_duplicate');

    const status = await request(server)
      .get(`/api/v1/sync/status?deviceId=${deviceA}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(status.body.conflict).toBeGreaterThanOrEqual(1);
  });

  it('does NOT flag two phones adding online (received before the next confirm)', async () => {
    // Online append path: each package is received as it is confirmed, so no
    // package predates another's confirmation.
    const awb = randomAwb();
    await createPackage(awb, {
      id: randomUUID(),
      ...WORKED,
      method: 'manual',
      weightSource: 'none',
      deviceId: deviceA,
      confirmedAt: new Date().toISOString(),
    }).expect(201);
    await createPackage(awb, {
      id: randomUUID(),
      ...WORKED,
      method: 'manual',
      weightSource: 'none',
      deviceId: deviceB,
      confirmedAt: new Date().toISOString(),
    }).expect(201);

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(detail.body.packages).toHaveLength(2);
    expect(detail.body.flags).not.toContain('possible_duplicate');
  });
});

describe('POST /sync/batch — shared-phone ownership', () => {
  it('rejects an item owned by a different user (OWNER_MISMATCH)', async () => {
    const awb = randomAwb();
    const mine = item(awb, { measuredBy: labour.userId });
    const theirs = item(awb, { measuredBy: randomUUID() });

    const res = await syncBatch([mine, theirs]).expect(200);
    const byId: Record<string, ResultRow> = Object.fromEntries(
      (res.body.results as ResultRow[]).map((r) => [r.id, r]),
    );
    expect(byId[mine.id].status).toBe('synced');
    expect(byId[theirs.id].status).toBe('failed');
    expect(byId[theirs.id].error?.code).toBe('OWNER_MISMATCH');
  });
});

describe('POST /sync/batch — renumber skips void/superseded numbers', () => {
  it('never reassigns a voided package number', async () => {
    const awb = randomAwb();
    // Two packages: PKG 01 and PKG 02.
    const t1 = new Date('2026-10-03T09:00:00.000Z').toISOString();
    const t2 = new Date('2026-10-03T09:01:00.000Z').toISOString();
    const first = await syncBatch([item(awb, { confirmedAt: t1 })]).expect(200);
    const second = await syncBatch([item(awb, { confirmedAt: t2 })]).expect(200);
    const p2Id = second.body.results[0].id as string;
    expect(first.body.results[0].packageNumber).toBe(1);
    expect(second.body.results[0].packageNumber).toBe(2);

    // Void PKG 02 directly (keeps its number reserved, PRD §8).
    await prisma.package.update({ where: { id: p2Id }, data: { status: 'void' } });

    // A new package must skip 2 and take 3.
    const t3 = new Date('2026-10-03T09:02:00.000Z').toISOString();
    const third = await syncBatch([item(awb, { confirmedAt: t3 })]).expect(200);
    expect(third.body.results[0].packageNumber).toBe(3);

    // PKG 01 is unchanged.
    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    const active = (detail.body.packages as Array<{ packageNumber: number; status: string }>)
      .filter((p) => p.status === 'active')
      .map((p) => p.packageNumber)
      .sort((a, b) => a - b);
    expect(active).toEqual([1, 3]);
  });
});

describe('POST /sync/batch — limits', () => {
  it('rejects a batch larger than 50 items', async () => {
    const awb = randomAwb();
    const packages = Array.from({ length: 51 }, () => item(awb));
    await syncBatch(packages).expect(400);
  });
});
