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
let tl: AuthContext;
let otherTl: AuthContext; // Team Leader of a different branch (denial tests)

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

function createPackage(auth: AuthContext, awb: string, body: Record<string, unknown>, key: string) {
  return request(server)
    .post(`/api/v1/shipments/${awb}/packages`)
    .set('Authorization', `Bearer ${auth.accessToken}`)
    .set('Idempotency-Key', key)
    .send(body);
}

/** Create a completed shipment with `n` packages; returns awb + package rows. */
async function completedShipment(n = 1) {
  const awb = randomAwb();
  const pkgs = [];
  for (let i = 0; i < n; i++) {
    const res = await createPackage(labour, awb, packageBody(), randomUUID()).expect(201);
    pkgs.push(res.body);
  }
  await request(server)
    .post(`/api/v1/shipments/${awb}/complete`)
    .set('Authorization', `Bearer ${labour.accessToken}`)
    .expect(200);
  return { awb, pkgs };
}

function auditCount(entityId: string, action: string) {
  return prisma.auditLog.count({ where: { entityId, action } });
}

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  await prisma.config.upsert({
    where: { key: 'actual_weight_required' },
    update: { value: false },
    create: { key: 'actual_weight_required', value: false, scope: 'global' },
  });
  const branchId = await createBranch(prisma, 'TLA');
  const otherBranchId = await createBranch(prisma, 'TLB');
  labour = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('TLA_LAB'),
    role: 'labour',
  });
  tl = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('TLA_TL'),
    role: 'team_leader',
  });
  otherTl = await createAndLogin(prisma, server, otherBranchId, {
    employeeId: uniqueEmployeeId('TLB_TL'),
    role: 'team_leader',
  });
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

describe('Corrections (PRD §8, §11)', () => {
  it('appends a new version, keeps v1, repoints current, recomputes totals, audits', async () => {
    const awb = randomAwb();
    const created = await createPackage(labour, awb, packageBody(), randomUUID()).expect(201);
    const pkgId = created.body.id;
    const v1Id = created.body.currentVersion.id;

    const res = await request(server)
      .post(`/api/v1/packages/${pkgId}/corrections`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ lengthMm: 500, widthMm: 400, heightMm: 300, reason: 'mismeasured on mat' })
      .expect(201);

    expect(res.body.status).toBe('active');
    expect(res.body.currentVersion.versionNo).toBe(2);
    expect(res.body.currentVersion.id).not.toBe(v1Id);
    expect(res.body.currentVersion.lengthMm).toBe(500);
    expect(res.body.currentVersion.billingLCm).toBe(50);
    expect(res.body.currentVersion.reason).toBe('mismeasured on mat');

    // v1 preserved (immutable history).
    const versions = await prisma.measurementVersion.findMany({ where: { packageId: pkgId } });
    expect(versions).toHaveLength(2);
    const v1 = versions.find((v) => v.id === v1Id)!;
    expect(v1.lengthMm).toBe(452);

    // Totals recomputed from the new current version.
    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .expect(200);
    expect(detail.body.totals.volumetricG).toBe(res.body.currentVersion.volumetricG);

    expect(await auditCount(pkgId, 'package_corrected')).toBe(1);
  });

  it('exposes version history (newest first) with the current version marked', async () => {
    const created = await createPackage(labour, randomAwb(), packageBody(), randomUUID()).expect(
      201,
    );
    const pkgId = created.body.id;
    await request(server)
      .post(`/api/v1/packages/${pkgId}/corrections`)
      .set(`Authorization`, `Bearer ${tl.accessToken}`)
      .send({ lengthMm: 480, widthMm: 320, heightMm: 220, reason: 'tweak' })
      .expect(201);

    const res = await request(server)
      .get(`/api/v1/packages/${pkgId}/versions`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .expect(200);
    expect(res.body.items).toHaveLength(2);
    expect(res.body.items[0].versionNo).toBe(2); // newest first
    expect(res.body.items[1].versionNo).toBe(1);
    expect(res.body.currentVersionId).toBe(res.body.items[0].id);
  });

  it('requires a reason (400)', async () => {
    const created = await createPackage(labour, randomAwb(), packageBody(), randomUUID()).expect(
      201,
    );
    await request(server)
      .post(`/api/v1/packages/${created.body.id}/corrections`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ lengthMm: 500, widthMm: 400, heightMm: 300 })
      .expect(400);
  });

  it('forbids Labour (403)', async () => {
    const created = await createPackage(labour, randomAwb(), packageBody(), randomUUID()).expect(
      201,
    );
    await request(server)
      .post(`/api/v1/packages/${created.body.id}/corrections`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send({ lengthMm: 500, widthMm: 400, heightMm: 300, reason: 'x' })
      .expect(403);
  });

  it('denies a Team Leader from another branch (404)', async () => {
    const created = await createPackage(labour, randomAwb(), packageBody(), randomUUID()).expect(
      201,
    );
    await request(server)
      .post(`/api/v1/packages/${created.body.id}/corrections`)
      .set('Authorization', `Bearer ${otherTl.accessToken}`)
      .send({ lengthMm: 500, widthMm: 400, heightMm: 300, reason: 'x' })
      .expect(404);
  });
});

describe('Void (PRD §8)', () => {
  it('voids a package, excludes it from totals, keeps its number, audits', async () => {
    const awb = randomAwb();
    const one = await createPackage(labour, awb, packageBody(), randomUUID()).expect(201);
    await createPackage(labour, awb, packageBody(), randomUUID()).expect(201);

    const res = await request(server)
      .post(`/api/v1/packages/${one.body.id}/void`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ reason: 'wrong AWB' })
      .expect(200);
    expect(res.body.status).toBe('void');
    expect(res.body.packageNumber).toBe(1); // number retained

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .expect(200);
    expect(detail.body.totals.pieces).toBe(1);

    expect(await auditCount(one.body.id, 'package_voided')).toBe(1);
  });

  it('rejects voiding an already-void package (409) and forbids Labour (403)', async () => {
    const created = await createPackage(labour, randomAwb(), packageBody(), randomUUID()).expect(
      201,
    );
    await request(server)
      .post(`/api/v1/packages/${created.body.id}/void`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send({ reason: 'x' })
      .expect(403);
    await request(server)
      .post(`/api/v1/packages/${created.body.id}/void`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ reason: 'dup' })
      .expect(200);
    await request(server)
      .post(`/api/v1/packages/${created.body.id}/void`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ reason: 'again' })
      .expect(409);
  });
});

describe('Reopen (PRD §8)', () => {
  it('reopens a completed shipment, rejects reopening an open one, audits', async () => {
    const { awb } = await completedShipment(1);

    const res = await request(server)
      .post(`/api/v1/shipments/${awb}/reopen`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ reason: 'add a missed piece' })
      .expect(200);
    expect(res.body.status).toBe('in_progress');
    expect(res.body.completedAt).toBeNull();

    // Reopening an in_progress shipment → 409.
    await request(server)
      .post(`/api/v1/shipments/${awb}/reopen`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ reason: 'again' })
      .expect(409);

    const shipment = await prisma.shipment.findFirstOrThrow({ where: { awb } });
    expect(await auditCount(shipment.id, 'shipment_reopened')).toBe(1);
  });

  it('forbids Labour (403)', async () => {
    const { awb } = await completedShipment(1);
    await request(server)
      .post(`/api/v1/shipments/${awb}/reopen`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send({ reason: 'x' })
      .expect(403);
  });
});

describe('Remeasurement loop (PRD §8)', () => {
  it('request → worker remeasures → old superseded, new active same number, shipment completed', async () => {
    const { awb, pkgs } = await completedShipment(2);
    const pkg1 = pkgs[0];

    // TL requests remeasurement of PKG 1.
    const shipment = await prisma.shipment.findFirstOrThrow({ where: { awb } });
    await request(server)
      .post('/api/v1/remeasurements')
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ shipmentId: shipment.id, packageIds: [pkg1.id], reason: 'customer_dispute' })
      .expect(201);

    const afterReq = await prisma.shipment.findFirstOrThrow({ where: { awb } });
    expect(afterReq.status).toBe('remeasure_required');

    // Labour completes the remeasurement.
    const res = await createPackage(
      labour,
      awb,
      packageBody({ remeasureOfPackageId: pkg1.id, lengthMm: 600 }),
      randomUUID(),
    ).expect(201);
    expect(res.body.status).toBe('active');
    expect(res.body.packageNumber).toBe(1); // SAME number as the superseded package

    const old = await prisma.package.findUniqueOrThrow({ where: { id: pkg1.id } });
    expect(old.status).toBe('superseded');

    // Only package requested → shipment returns to completed, request done.
    const done = await prisma.shipment.findFirstOrThrow({ where: { awb } });
    expect(done.status).toBe('completed');
    const req = await prisma.remeasureRequest.findFirstOrThrow({
      where: { shipmentId: shipment.id },
    });
    expect(req.status).toBe('done');

    // Totals still 2 active pieces (new PKG1' + PKG2).
    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .expect(200);
    expect(detail.body.totals.pieces).toBe(2);

    expect(await auditCount(pkg1.id, 'package_remeasured')).toBe(1);
    expect(await auditCount(shipment.id, 'remeasure_completed')).toBe(1);
  });

  it('rejects a remeasure capture when no open request names the package (409)', async () => {
    const { awb, pkgs } = await completedShipment(1);
    await createPackage(
      labour,
      awb,
      packageBody({ remeasureOfPackageId: pkgs[0].id }),
      randomUUID(),
    ).expect(409);
  });

  it('cancelling an open request returns the shipment to completed', async () => {
    const { awb, pkgs } = await completedShipment(1);
    const shipment = await prisma.shipment.findFirstOrThrow({ where: { awb } });
    const req = await request(server)
      .post('/api/v1/remeasurements')
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ shipmentId: shipment.id, packageIds: [pkgs[0].id], reason: 'bad_photo' })
      .expect(201);
    await request(server)
      .post(`/api/v1/remeasurements/${req.body.id}/cancel`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .expect(200);
    const back = await prisma.shipment.findFirstOrThrow({ where: { awb } });
    expect(back.status).toBe('completed');
  });
});

describe('Flags triage (PRD §11)', () => {
  it('worker flag appears in GET /flags; resolve closes it and prunes the summary', async () => {
    const { awb } = await completedShipment(1);
    const shipment = await prisma.shipment.findFirstOrThrow({ where: { awb } });

    // Labour "Flag for Team Leader".
    const flagRes = await request(server)
      .post('/api/v1/flags')
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send({ shipmentId: shipment.id, note: 'looks squashed' })
      .expect(201);
    const flagId = flagRes.body.id;

    // Appears in the queue for the TL.
    const queue = await request(server)
      .get('/api/v1/flags?status=open')
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .expect(200);
    expect(queue.body.items.some((f: { id: string }) => f.id === flagId)).toBe(true);

    // Shipment summary carries the type.
    const withFlag = await prisma.shipment.findFirstOrThrow({ where: { id: shipment.id } });
    expect(withFlag.flags).toContain('worker_flag');

    // Resolve (approve) → status resolved, summary pruned, audited.
    const resolved = await request(server)
      .post(`/api/v1/flags/${flagId}/resolve`)
      .set('Authorization', `Bearer ${tl.accessToken}`)
      .send({ action: 'approve', note: 'remeasured, fine' })
      .expect(200);
    expect(resolved.body.status).toBe('resolved');

    const pruned = await prisma.shipment.findFirstOrThrow({ where: { id: shipment.id } });
    expect(pruned.flags).not.toContain('worker_flag');
    expect(await auditCount(flagId, 'flag_resolved')).toBe(1);
  });

  it('forbids Labour from the review queue (403)', async () => {
    await request(server)
      .get('/api/v1/flags')
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(403);
  });

  it('denies a Team Leader resolving a flag in another branch (404)', async () => {
    const { awb } = await completedShipment(1);
    const shipment = await prisma.shipment.findFirstOrThrow({ where: { awb } });
    const flagRes = await request(server)
      .post('/api/v1/flags')
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send({ shipmentId: shipment.id, note: 'x' })
      .expect(201);
    await request(server)
      .post(`/api/v1/flags/${flagRes.body.id}/resolve`)
      .set('Authorization', `Bearer ${otherTl.accessToken}`)
      .send({ action: 'dismiss' })
      .expect(404);
  });
});
