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

/** Worked example (PRD §7): 45.2 × 30.1 × 20.4 cm. */
const WORKED = { lengthMm: 452, widthMm: 301, heightMm: 204 };

function packageBody(extra: Record<string, unknown> = {}) {
  return {
    id: randomUUID(),
    ...WORKED,
    method: 'manual',
    weightSource: 'none',
    confirmedAt: new Date().toISOString(),
    ...extra,
  };
}

function createPackage(awb: string, body: Record<string, unknown>, key: string) {
  return request(server)
    .post(`/api/v1/shipments/${awb}/packages`)
    .set('Authorization', `Bearer ${labour.accessToken}`)
    .set('Idempotency-Key', key)
    .send(body);
}

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  const branchId = await createBranch(prisma, 'CAP');
  labour = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('CAP_LAB'),
    role: 'labour',
  });
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

describe('AWB lookup', () => {
  it('reports found=false and nextPackageNumber=1 for a new AWB', async () => {
    const awb = randomAwb();
    const res = await request(server)
      .get(`/api/v1/awb/${awb}/lookup`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(res.body.found).toBe(false);
    expect(res.body.shipment).toBeNull();
    expect(res.body.nextPackageNumber).toBe(1);
  });

  it('rejects a malformed AWB with 400', async () => {
    await request(server)
      .get('/api/v1/awb/AY123/lookup')
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(400);
  });
});

describe('Package creation — numbering, billing, server authority', () => {
  it('creates the shipment and PKG 01 with server-computed billing', async () => {
    const awb = randomAwb();
    const res = await createPackage(awb, packageBody(), randomUUID()).expect(201);

    expect(res.body.packageNumber).toBe(1);
    expect(res.body.status).toBe('active');
    const v = res.body.currentVersion;
    expect(v.billingLCm).toBe(46);
    expect(v.billingWCm).toBe(31);
    expect(v.billingHCm).toBe(21);
    expect(v.cbm).toBeCloseTo(0.0299, 4);
    expect(v.volumetricG).toBe(5989);
    expect(v.chargeableG).toBe(6000); // no actual weight → volumetric wins
    expect(v.divisorUsed).toBe(5000);
    expect(v.weightSource).toBe('none');
    expect(v.method).toBe('manual');
    expect(v.confidence).toBeNull();
    expect(v.versionNo).toBe(1);

    const lookup = await request(server)
      .get(`/api/v1/awb/${awb}/lookup`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(lookup.body.found).toBe(true);
    expect(lookup.body.shipment.status).toBe('in_progress');
    expect(lookup.body.nextPackageNumber).toBe(2);
    expect(lookup.body.shipment.packages).toHaveLength(1);
  });

  it('rejects client-sent billing fields outright (server is final)', async () => {
    // The create DTO carries base units only; billing is never accepted from the
    // client. The strict validation pipe rejects such fields with 400.
    const awb = randomAwb();
    await createPackage(
      awb,
      packageBody({ billingLCm: 999, cbm: 123, chargeableG: 1 }),
      randomUUID(),
    ).expect(400);
  });

  it('assigns sequential package numbers within a shipment', async () => {
    const awb = randomAwb();
    const one = await createPackage(awb, packageBody(), randomUUID()).expect(201);
    const two = await createPackage(awb, packageBody(), randomUUID()).expect(201);
    expect(one.body.packageNumber).toBe(1);
    expect(two.body.packageNumber).toBe(2);
  });

  it('rejects a dimension outside the configured range (400)', async () => {
    const awb = randomAwb();
    const res = await createPackage(
      awb,
      packageBody({ lengthMm: 5 }), // 0.5 cm < 1 cm
      randomUUID(),
    ).expect(400);
    expect(res.body.code).toBe('DIMENSION_OUT_OF_RANGE');
  });

  it('rejects a create without an Idempotency-Key (400)', async () => {
    const awb = randomAwb();
    await request(server)
      .post(`/api/v1/shipments/${awb}/packages`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send(packageBody())
      .expect(400);
  });

  it('rejects a malformed AWB on create (400)', async () => {
    await createPackage('AY123', packageBody(), randomUUID()).expect(400);
  });
});

describe('Idempotency (PRD §10)', () => {
  it('returns the original package on replay (200, no duplicate)', async () => {
    const awb = randomAwb();
    const body = packageBody();
    const key = randomUUID();

    const first = await createPackage(awb, body, key).expect(201);
    const replay = await createPackage(awb, body, key).expect(200);
    expect(replay.body.id).toBe(first.body.id);
    expect(replay.body.packageNumber).toBe(first.body.packageNumber);

    // Same Idempotency-Key with different content still returns the original.
    const replay2 = await createPackage(
      awb,
      packageBody({ id: body.id, heightMm: 999 }),
      key,
    ).expect(200);
    expect(replay2.body.id).toBe(first.body.id);
    expect(replay2.body.currentVersion.heightMm).toBe(204);

    const lookup = await request(server)
      .get(`/api/v1/awb/${awb}/lookup`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(lookup.body.shipment.packages).toHaveLength(1);
  });
});

describe('Shipment state machine (PRD §8)', () => {
  it('completes an in-progress shipment, then rejects further transitions', async () => {
    const awb = randomAwb();
    await createPackage(awb, packageBody(), randomUUID()).expect(201);
    await createPackage(awb, packageBody(), randomUUID()).expect(201);

    const completed = await request(server)
      .post(`/api/v1/shipments/${awb}/complete`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(completed.body.status).toBe('completed');
    expect(completed.body.totals.pieces).toBe(2);
    expect(completed.body.completedAt).toBeTruthy();

    // Double complete → 409.
    await request(server)
      .post(`/api/v1/shipments/${awb}/complete`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(409);

    // Add a package to a completed shipment → 409.
    const blocked = await createPackage(awb, packageBody(), randomUUID()).expect(409);
    expect(blocked.body.code).toBe('SHIPMENT_NOT_OPEN');
  });

  it('totals are the sum of active packages', async () => {
    const awb = randomAwb();
    await createPackage(awb, packageBody(), randomUUID()).expect(201);
    await createPackage(awb, packageBody(), randomUUID()).expect(201);
    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(detail.body.totals.pieces).toBe(2);
    expect(detail.body.totals.volumetricG).toBe(5989 * 2);
    expect(detail.body.totals.chargeableG).toBe(6000 * 2);
    expect(detail.body.totals.cbm).toBeCloseTo(0.0598, 4);
  });
});

describe('Concurrent package numbering (finding 3)', () => {
  it('assigns PKG 01–05 for five concurrent creates, no errors', async () => {
    const awb = randomAwb();
    const results = await Promise.all(
      Array.from({ length: 5 }, () => createPackage(awb, packageBody(), randomUUID())),
    );

    for (const res of results) {
      expect(res.status).toBe(201);
    }
    const numbers = results.map((r) => r.body.packageNumber).sort((a, b) => a - b);
    expect(numbers).toEqual([1, 2, 3, 4, 5]);
  });
});
