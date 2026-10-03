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
  it('keeps both packages and flags the shipment for the Team Leader', async () => {
    const awb = randomAwb();
    const a = item(awb, { deviceId: deviceA });
    const b = item(awb, { deviceId: deviceB });

    const res = await syncBatch([a, b]).expect(200);
    const statuses = (res.body.results as ResultRow[]).map((r) => r.status);
    expect(statuses).toContain('conflict'); // the second device triggers the flag

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(detail.body.packages).toHaveLength(2);
    expect(detail.body.flags).toContain('possible_duplicate');

    // The server's sync status echoes the conflict for the device.
    const status = await request(server)
      .get(`/api/v1/sync/status?deviceId=${deviceA}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(status.body.conflict).toBeGreaterThanOrEqual(1);
  });
});

describe('POST /sync/batch — limits', () => {
  it('rejects a batch larger than 50 items', async () => {
    const awb = randomAwb();
    const packages = Array.from({ length: 51 }, () => item(awb));
    await syncBatch(packages).expect(400);
  });
});
