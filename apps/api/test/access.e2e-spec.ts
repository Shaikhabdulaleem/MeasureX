import { INestApplication } from '@nestjs/common';
import { randomUUID } from 'crypto';
import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { AutoCompleteService } from '../src/jobs/auto-complete.service';
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

let branchA: string;
let branchB: string;
let labourA: AuthContext;
let labourA2: AuthContext;
let labourB: AuthContext;
let tlA: AuthContext;
let tlB: AuthContext;
let adminAll: AuthContext;
let adminNull: AuthContext;

const WORKED = { lengthMm: 452, widthMm: 301, heightMm: 204 };

function body(extra: Record<string, unknown> = {}) {
  return {
    id: randomUUID(),
    ...WORKED,
    method: 'manual',
    weightSource: 'none',
    confirmedAt: new Date().toISOString(),
    ...extra,
  };
}

function createPackage(token: string, awb: string, extra: Record<string, unknown> = {}) {
  return request(server)
    .post(`/api/v1/shipments/${awb}/packages`)
    .set('Authorization', `Bearer ${token}`)
    .set('Idempotency-Key', randomUUID())
    .send(body(extra));
}

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  branchA = await createBranch(prisma, 'ACC_A');
  branchB = await createBranch(prisma, 'ACC_B');
  labourA = await createAndLogin(prisma, server, branchA, {
    employeeId: uniqueEmployeeId('ACC_LABA'),
    role: 'labour',
  });
  labourA2 = await createAndLogin(prisma, server, branchA, {
    employeeId: uniqueEmployeeId('ACC_LABA2'),
    role: 'labour',
  });
  tlA = await createAndLogin(prisma, server, branchA, {
    employeeId: uniqueEmployeeId('ACC_TLA'),
    role: 'team_leader',
  });
  tlB = await createAndLogin(prisma, server, branchB, {
    employeeId: uniqueEmployeeId('ACC_TLB'),
    role: 'team_leader',
  });
  labourB = await createAndLogin(prisma, server, branchB, {
    employeeId: uniqueEmployeeId('ACC_LABB'),
    role: 'labour',
  });
  adminAll = await createAndLogin(prisma, server, branchA, {
    employeeId: uniqueEmployeeId('ACC_ADMIN'),
    role: 'admin',
    adminScope: 'all',
  });
  adminNull = await createAndLogin(prisma, server, branchA, {
    employeeId: uniqueEmployeeId('ACC_ADMIN_NULL'),
    role: 'admin',
    adminScope: undefined, // stored as null → fail-closed, sees nothing
  });
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

describe('Role + branch access (PRD §3, §10, §14)', () => {
  it('scopes shipment detail to branch for team leaders', async () => {
    const awb = randomAwb();
    await createPackage(labourA.accessToken, awb).expect(201);

    // Team Leader in the same branch can see it.
    await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);

    // Team Leader in another branch cannot.
    await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tlB.accessToken}`)
      .expect(404);

    // Admin scoped to "all" can.
    await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${adminAll.accessToken}`)
      .expect(200);
  });

  it('limits labour to their own measurements', async () => {
    const awb = randomAwb();
    await createPackage(labourA.accessToken, awb).expect(201);

    // The measuring labour sees it.
    await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .expect(200);

    // Another labour in the same branch does not.
    await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${labourA2.accessToken}`)
      .expect(404);
  });

  it('requires authentication', async () => {
    await request(server).get('/api/v1/shipments').expect(401);
  });
});

describe('Photos (PRD §6)', () => {
  it('issues an upload target, and gates the view URL to TL/Admin', async () => {
    const awb = randomAwb();
    const pkg = await createPackage(labourA.accessToken, awb).expect(201);

    const target = await request(server)
      .post(`/api/v1/packages/${pkg.body.id}/photos`)
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .send({ kind: 'raw', contentType: 'image/jpeg', bytes: 123456 })
      .expect(201);
    expect(target.body.photoId).toBeTruthy();
    expect(target.body.uploadUrl).toContain('http');
    expect(target.body.method).toBe('PUT');

    const photoId = target.body.photoId;

    // Labour cannot view (personal data on the label).
    await request(server)
      .get(`/api/v1/photos/${photoId}`)
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .expect(403);

    // Team Leader can, and the view is signed + logged.
    const view = await request(server)
      .get(`/api/v1/photos/${photoId}`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);
    expect(view.body.url).toContain('http');
    expect(view.body.expiresAt).toBeTruthy();

    const audit = await prisma.auditLog.findFirst({
      where: { entity: 'photo', entityId: photoId, action: 'photo_viewed' },
    });
    expect(audit).not.toBeNull();
  });

  it('scopes the photo view URL to the branch (finding 1)', async () => {
    const awb = randomAwb();
    const pkg = await createPackage(labourA.accessToken, awb).expect(201);
    const target = await request(server)
      .post(`/api/v1/packages/${pkg.body.id}/photos`)
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .send({ contentType: 'image/jpeg' })
      .expect(201);
    const photoId = target.body.photoId;

    // TL in another branch cannot view (out of scope → 404, not 403).
    await request(server)
      .get(`/api/v1/photos/${photoId}`)
      .set('Authorization', `Bearer ${tlB.accessToken}`)
      .expect(404);

    // Admin with no scope sees nothing either.
    await request(server)
      .get(`/api/v1/photos/${photoId}`)
      .set('Authorization', `Bearer ${adminNull.accessToken}`)
      .expect(404);

    // TL in the shipment's branch can.
    await request(server)
      .get(`/api/v1/photos/${photoId}`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);
  });

  it('authorises the upload target and audits the request (finding 2)', async () => {
    const awb = randomAwb();
    const pkg = await createPackage(labourA.accessToken, awb).expect(201);

    // A different labour who did not measure the package cannot attach a photo.
    await request(server)
      .post(`/api/v1/packages/${pkg.body.id}/photos`)
      .set('Authorization', `Bearer ${labourA2.accessToken}`)
      .send({ contentType: 'image/jpeg' })
      .expect(403);

    // A TL in another branch cannot either (out of scope).
    await request(server)
      .post(`/api/v1/packages/${pkg.body.id}/photos`)
      .set('Authorization', `Bearer ${tlB.accessToken}`)
      .send({ contentType: 'image/jpeg' })
      .expect(403);

    // The measurer can, and the request is audited.
    const target = await request(server)
      .post(`/api/v1/packages/${pkg.body.id}/photos`)
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .send({ contentType: 'image/jpeg' })
      .expect(201);
    const audit = await prisma.auditLog.findFirst({
      where: {
        entity: 'photo',
        entityId: target.body.photoId,
        action: 'photo_upload_requested',
      },
    });
    expect(audit).not.toBeNull();

    // A TL within the shipment's branch can also attach.
    await request(server)
      .post(`/api/v1/packages/${pkg.body.id}/photos`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .send({ contentType: 'image/jpeg' })
      .expect(201);
  });
});

describe('Cross-branch package add (finding 4)', () => {
  it('rejects adding to another branch, but a scoped admin may override', async () => {
    const awb = randomAwb();
    // Shipment created in branch A by labourA.
    await createPackage(labourA.accessToken, awb).expect(201);

    // Labour in branch B cannot add a package → 409 SHIPMENT_OTHER_BRANCH.
    const blocked = await createPackage(labourB.accessToken, awb).expect(409);
    expect(blocked.body.code).toBe('SHIPMENT_OTHER_BRANCH');

    // TL in branch B is also confined to their home branch.
    const blockedTl = await createPackage(tlB.accessToken, awb).expect(409);
    expect(blockedTl.body.code).toBe('SHIPMENT_OTHER_BRANCH');

    // Admin scoped to all branches may add across branches.
    await createPackage(adminAll.accessToken, awb).expect(201);
  });
});

describe('Admin scope fail-closed (finding 5)', () => {
  it('an admin with no scope sees no shipments', async () => {
    const awb = randomAwb();
    await createPackage(labourA.accessToken, awb).expect(201);

    // Detail is 404 (not found within an empty scope).
    await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${adminNull.accessToken}`)
      .expect(404);

    // The list excludes everything for a scopeless admin.
    const list = await request(server)
      .get('/api/v1/shipments')
      .set('Authorization', `Bearer ${adminNull.accessToken}`)
      .expect(200);
    expect(list.body.items).toHaveLength(0);
  });
});

describe('Flag + remeasure (buttons/endpoints, PRD §5, §8)', () => {
  it('lets Labour flag a shipment for the Team Leader', async () => {
    const awb = randomAwb();
    const pkg = await createPackage(labourA.accessToken, awb).expect(201);

    const flag = await request(server)
      .post('/api/v1/flags')
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .send({ shipmentId: pkg.body.shipmentId, note: 'Looks wrong' })
      .expect(201);
    expect(flag.body.type).toBe('worker_flag');

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);
    expect(detail.body.flags).toContain('worker_flag');
  });

  it('enforces role on remeasurement and drives the shipment state', async () => {
    const awb = randomAwb();
    await createPackage(labourA.accessToken, awb).expect(201);
    const pkgDetail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);
    const shipmentId = pkgDetail.body.id;
    const packageId = pkgDetail.body.packages[0].id;

    await request(server)
      .post(`/api/v1/shipments/${awb}/complete`)
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .expect(200);

    // Labour cannot request a remeasurement.
    await request(server)
      .post('/api/v1/remeasurements')
      .set('Authorization', `Bearer ${labourA.accessToken}`)
      .send({ shipmentId, packageIds: [packageId], reason: 'bad_photo' })
      .expect(403);

    // Team Leader can; shipment → remeasure_required.
    const req = await request(server)
      .post('/api/v1/remeasurements')
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .send({ shipmentId, packageIds: [packageId], reason: 'bad_photo' })
      .expect(201);
    expect(req.body.status).toBe('open');

    let detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);
    expect(detail.body.status).toBe('remeasure_required');

    // Cancelling returns it to completed.
    await request(server)
      .post(`/api/v1/remeasurements/${req.body.id}/cancel`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);
    detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${tlA.accessToken}`)
      .expect(200);
    expect(detail.body.status).toBe('completed');
  });
});

describe('Idle auto-complete (PRD §5, §8)', () => {
  it('completes an in-progress shipment left idle beyond the threshold', async () => {
    const awb = randomAwb();
    await createPackage(labourA.accessToken, awb).expect(201);
    const shipment = await prisma.shipment.findFirstOrThrow({ where: { awb } });

    // Age the shipment past the 30-min idle threshold (bypass @updatedAt).
    const past = new Date(Date.now() - 40 * 60_000);
    await prisma.$executeRaw`UPDATE shipment SET updated_at = ${past} WHERE id = ${shipment.id}::uuid`;

    const completed = await app.get(AutoCompleteService).completeIdleShipments();
    expect(completed).toBeGreaterThanOrEqual(1);

    const after = await prisma.shipment.findFirstOrThrow({ where: { id: shipment.id } });
    expect(after.status).toBe('completed');
    expect(after.completedAt).not.toBeNull();

    const audit = await prisma.auditLog.findFirst({
      where: { entity: 'shipment', entityId: shipment.id, action: 'shipment_auto_completed' },
    });
    expect(audit).not.toBeNull();
  });
});
