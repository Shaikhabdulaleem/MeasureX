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
let teamLeader: AuthContext;
let admin: AuthContext;
let approvedScaleId: string;

const WORKED = { lengthMm: 452, widthMm: 301, heightMm: 204 };

function packageBody(extra: Record<string, unknown> = {}) {
  return {
    id: randomUUID(),
    ...WORKED,
    method: 'manual',
    confirmedAt: new Date().toISOString(),
    ...extra,
  };
}

function createPackage(
  auth: AuthContext,
  awb: string,
  body: Record<string, unknown>,
  key = randomUUID(),
) {
  return request(server)
    .post(`/api/v1/shipments/${awb}/packages`)
    .set('Authorization', `Bearer ${auth.accessToken}`)
    .set('Idempotency-Key', key)
    .send(body);
}

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  // M2 default: actual weight is required to save (PRD A6).
  await prisma.config.upsert({
    where: { key: 'actual_weight_required' },
    update: { value: true },
    create: { key: 'actual_weight_required', value: true, scope: 'global' },
  });

  const branchId = await createBranch(prisma, 'SCL');
  labour = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('SCL_LAB'),
    role: 'labour',
  });
  teamLeader = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('SCL_TL'),
    role: 'team_leader',
  });
  admin = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('SCL_ADM'),
    role: 'admin',
    adminScope: 'all',
  });
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

describe('Scales CRUD and authorization (PRD §9, §13)', () => {
  it('rejects scale creation by a labour user (403)', async () => {
    await request(server)
      .post('/api/v1/scales')
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send({ model: 'Nope', connection: 'ble', adapterKey: 'ble' })
      .expect(403);
  });

  it('lets an admin create a scale and defaults its stability thresholds', async () => {
    const res = await request(server)
      .post('/api/v1/scales')
      .set('Authorization', `Bearer ${admin.accessToken}`)
      .send({ model: 'Acme BLE 100', connection: 'ble', adapterKey: 'ble' })
      .expect(201);
    expect(res.body.approved).toBe(false);
    // PRD §9 defaults.
    expect(res.body.stabilityWindow).toBe(5);
    expect(res.body.stabilityToleranceG).toBe(20);
    expect(res.body.stabilityWindowMs).toBe(1500);
    expect(res.body.minWeightG).toBe(50);
    expect(res.body.staleAfterMs).toBe(5000);
    // BLE/Classic default to streaming; HID defaults to one-shot (PRD §9).
    expect(res.body.streaming).toBe(true);
    approvedScaleId = res.body.id;
  });

  it('defaults a HID scale to one-shot and honours an explicit override', async () => {
    const hid = await request(server)
      .post('/api/v1/scales')
      .set('Authorization', `Bearer ${admin.accessToken}`)
      .send({ model: 'HID One-shot', connection: 'hid', adapterKey: 'hid' })
      .expect(201);
    expect(hid.body.streaming).toBe(false);

    const overridden = await request(server)
      .post('/api/v1/scales')
      .set('Authorization', `Bearer ${admin.accessToken}`)
      .send({ model: 'HID Streaming', connection: 'hid', adapterKey: 'hid', streaming: true })
      .expect(201);
    expect(overridden.body.streaming).toBe(true);
  });

  it('hides unapproved scales from the default list but shows them to admin with all=true', async () => {
    const asLabour = await request(server)
      .get('/api/v1/scales')
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(asLabour.body.find((s: { id: string }) => s.id === approvedScaleId)).toBeUndefined();

    const asAdmin = await request(server)
      .get('/api/v1/scales?all=true')
      .set('Authorization', `Bearer ${admin.accessToken}`)
      .expect(200);
    expect(asAdmin.body.find((s: { id: string }) => s.id === approvedScaleId)).toBeDefined();
  });

  it('lets an admin approve and tune thresholds (audited)', async () => {
    const res = await request(server)
      .patch(`/api/v1/scales/${approvedScaleId}`)
      .set('Authorization', `Bearer ${admin.accessToken}`)
      .send({ approved: true, stabilityToleranceG: 15 })
      .expect(200);
    expect(res.body.approved).toBe(true);
    expect(res.body.stabilityToleranceG).toBe(15);

    const audit = await prisma.auditLog.findFirst({
      where: { entity: 'scale', entityId: approvedScaleId, action: 'scale_updated' },
    });
    expect(audit).not.toBeNull();

    // Now visible in the default (approved-only) list.
    const list = await request(server)
      .get('/api/v1/scales')
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(list.body.find((s: { id: string }) => s.id === approvedScaleId)).toBeDefined();
  });
});

describe('Scale weight rules on package create (PRD §9)', () => {
  it('saves a package with an approved scale weight', async () => {
    const awb = randomAwb();
    const res = await createPackage(labour, awb, {
      ...packageBody(),
      weightSource: 'scale',
      scaleId: approvedScaleId,
      actualWeightG: 4800,
    }).expect(201);
    expect(res.body.currentVersion.weightSource).toBe('scale');
    expect(res.body.currentVersion.actualWeightG).toBe(4800);
    // Worked example: actual 4.8 kg < volumetric 5.99 kg → chargeable 6.0 kg.
    expect(res.body.currentVersion.chargeableG).toBe(6000);
  });

  it('rejects weightSource=scale without a scaleId (400)', async () => {
    const awb = randomAwb();
    const res = await createPackage(labour, awb, {
      ...packageBody(),
      weightSource: 'scale',
      actualWeightG: 4800,
    }).expect(400);
    expect(res.body.code).toBe('SCALE_ID_REQUIRED');
  });

  it('rejects weightSource=scale with an unapproved scaleId (400)', async () => {
    const unapproved = await request(server)
      .post('/api/v1/scales')
      .set('Authorization', `Bearer ${admin.accessToken}`)
      .send({ model: 'Unapproved', connection: 'hid', adapterKey: 'hid' })
      .expect(201);

    const awb = randomAwb();
    const res = await createPackage(labour, awb, {
      ...packageBody(),
      weightSource: 'scale',
      scaleId: unapproved.body.id,
      actualWeightG: 4800,
    }).expect(400);
    expect(res.body.code).toBe('SCALE_NOT_APPROVED');
  });

  it('rejects weightSource=scale without a weight value (400)', async () => {
    const awb = randomAwb();
    const res = await createPackage(labour, awb, {
      ...packageBody(),
      weightSource: 'scale',
      scaleId: approvedScaleId,
    }).expect(400);
    expect(res.body.code).toBe('WEIGHT_REQUIRED');
  });

  it('rejects a save with no weight when actual_weight_required is on (400)', async () => {
    const awb = randomAwb();
    const res = await createPackage(labour, awb, {
      ...packageBody(),
      weightSource: 'none',
    }).expect(400);
    expect(res.body.code).toBe('WEIGHT_REQUIRED');
  });
});

describe('Manual weight permissions (PRD §9)', () => {
  it('forbids a labour user from entering manual weight (403)', async () => {
    const awb = randomAwb();
    const res = await createPackage(labour, awb, {
      ...packageBody(),
      weightSource: 'manual',
      actualWeightG: 4800,
      weightReason: 'scale offline',
    }).expect(403);
    expect(res.body.code).toBe('MANUAL_WEIGHT_FORBIDDEN');
  });

  it('requires a reason for manual weight (400)', async () => {
    const awb = randomAwb();
    const res = await createPackage(teamLeader, awb, {
      ...packageBody(),
      weightSource: 'manual',
      actualWeightG: 4800,
    }).expect(400);
    expect(res.body.code).toBe('WEIGHT_REASON_REQUIRED');
  });

  it('lets a Team Leader enter manual weight → manual_weight flag + audit', async () => {
    const awb = randomAwb();
    const pkg = await createPackage(teamLeader, awb, {
      ...packageBody(),
      weightSource: 'manual',
      actualWeightG: 4800,
      weightReason: 'scale offline',
    }).expect(201);
    expect(pkg.body.currentVersion.weightSource).toBe('manual');

    const detail = await request(server)
      .get(`/api/v1/shipments/${awb}`)
      .set('Authorization', `Bearer ${teamLeader.accessToken}`)
      .expect(200);
    expect(detail.body.flags).toContain('manual_weight');

    const flag = await prisma.flag.findFirst({
      where: { packageId: pkg.body.id, type: 'manual_weight' },
    });
    expect(flag).not.toBeNull();
    expect(flag?.note).toBe('scale offline');

    const audit = await prisma.auditLog.findFirst({
      where: { entity: 'package', entityId: pkg.body.id, action: 'manual_weight_entered' },
    });
    expect(audit).not.toBeNull();
    expect(audit?.reason).toBe('scale offline');
  });
});
