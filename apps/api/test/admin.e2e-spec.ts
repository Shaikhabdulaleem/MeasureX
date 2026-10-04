import { INestApplication } from '@nestjs/common';
import { randomUUID } from 'crypto';
import request from 'supertest';
import ExcelJS from 'exceljs';
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
let branchId: string;
let otherBranchId: string;
let admin: AuthContext;
let scopedAdmin: AuthContext; // admin scoped to `branchId` only
let tl: AuthContext;
let labour: AuthContext;

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

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  await prisma.config.upsert({
    where: { key: 'actual_weight_required' },
    update: { value: false },
    create: { key: 'actual_weight_required', value: false, scope: 'global' },
  });
  branchId = await createBranch(prisma, 'ADM');
  otherBranchId = await createBranch(prisma, 'ADM2');
  admin = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('ADM_ADMIN'),
    role: 'admin',
    adminScope: 'all',
  });
  scopedAdmin = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('ADM_SCOPED'),
    role: 'admin',
    adminScope: [branchId],
  });
  tl = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('ADM_TL'),
    role: 'team_leader',
  });
  labour = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('ADM_LAB'),
    role: 'labour',
  });
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

const authHeader = (a: AuthContext) => ({ Authorization: `Bearer ${a.accessToken}` });

describe('Users CRUD (Admin, PRD §3)', () => {
  it('creates a user with a temp password + mustChangePassword, audits', async () => {
    const empId = uniqueEmployeeId('NEWUSER');
    const res = await request(server)
      .post('/api/v1/users')
      .set(authHeader(admin))
      .send({ employeeId: empId, name: 'New Worker', role: 'labour', homeBranchId: branchId })
      .expect(201);
    expect(res.body.mustChangePassword).toBe(true);
    expect(res.body.tempPassword).toBeTruthy();
    expect(res.body).not.toHaveProperty('passwordHash');

    // The temp password actually works for login.
    await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: empId, password: res.body.tempPassword })
      .expect(200);

    expect(
      await prisma.auditLog.count({ where: { entityId: res.body.id, action: 'user_created' } }),
    ).toBe(1);
  });

  it('resets a password and unlocks, each audited', async () => {
    const empId = uniqueEmployeeId('LOCKME');
    const created = await request(server)
      .post('/api/v1/users')
      .set(authHeader(admin))
      .send({ employeeId: empId, name: 'Lock Me', role: 'labour', homeBranchId: branchId })
      .expect(201);
    const id = created.body.id;

    const reset = await request(server)
      .post(`/api/v1/users/${id}/reset-password`)
      .set(authHeader(admin))
      .send({})
      .expect(200);
    expect(reset.body.tempPassword).toBeTruthy();

    await request(server)
      .post(`/api/v1/users/${id}/unlock`)
      .set(authHeader(admin))
      .send({})
      .expect(200);

    expect(
      await prisma.auditLog.count({ where: { entityId: id, action: 'user_password_reset' } }),
    ).toBe(1);
    expect(await prisma.auditLog.count({ where: { entityId: id, action: 'user_unlocked' } })).toBe(
      1,
    );
  });

  it('forbids Team Leader and Labour from user management (403)', async () => {
    await request(server).get('/api/v1/users').set(authHeader(tl)).expect(403);
    await request(server).get('/api/v1/users').set(authHeader(labour)).expect(403);
  });
});

describe('Admin privilege escalation (PRD §3, §14)', () => {
  it('a scoped admin cannot create an "all" admin', async () => {
    const res = await request(server)
      .post('/api/v1/users')
      .set(authHeader(scopedAdmin))
      .send({
        employeeId: uniqueEmployeeId('ESC_ALL'),
        name: 'x',
        role: 'admin',
        homeBranchId: branchId,
        adminScope: ['all'],
      })
      .expect(403);
    expect(res.body.code).toBe('SCOPE_ESCALATION');
  });

  it('a scoped admin cannot grant a branch outside their scope', async () => {
    const res = await request(server)
      .post('/api/v1/users')
      .set(authHeader(scopedAdmin))
      .send({
        employeeId: uniqueEmployeeId('ESC_BR'),
        name: 'x',
        role: 'admin',
        homeBranchId: branchId,
        adminScope: [branchId, otherBranchId],
      })
      .expect(403);
    expect(res.body.code).toBe('SCOPE_ESCALATION');
  });

  it('a scoped admin CAN create an admin scoped to their own branch', async () => {
    await request(server)
      .post('/api/v1/users')
      .set(authHeader(scopedAdmin))
      .send({
        employeeId: uniqueEmployeeId('ESC_OK'),
        name: 'x',
        role: 'admin',
        homeBranchId: branchId,
        adminScope: [branchId],
      })
      .expect(201);
  });

  it('an "all" admin can create an "all" admin', async () => {
    await request(server)
      .post('/api/v1/users')
      .set(authHeader(admin))
      .send({
        employeeId: uniqueEmployeeId('ALL_ALL'),
        name: 'x',
        role: 'admin',
        homeBranchId: branchId,
        adminScope: ['all'],
      })
      .expect(201);
  });

  it('no one may change their own role or admin scope', async () => {
    const res = await request(server)
      .patch(`/api/v1/users/${scopedAdmin.userId}`)
      .set(authHeader(scopedAdmin))
      .send({ role: 'labour' })
      .expect(403);
    expect(res.body.code).toBe('CANNOT_EDIT_SELF');

    await request(server)
      .patch(`/api/v1/users/${scopedAdmin.userId}`)
      .set(authHeader(scopedAdmin))
      .send({ adminScope: ['all'] })
      .expect(403);
  });

  it('promoting a user to admin via update enforces the subset rule', async () => {
    // A plain labour user the scoped admin may manage (same branch).
    const target = await request(server)
      .post('/api/v1/users')
      .set(authHeader(scopedAdmin))
      .send({
        employeeId: uniqueEmployeeId('PROMO'),
        name: 'x',
        role: 'labour',
        homeBranchId: branchId,
      })
      .expect(201);

    // Promote to admin with an out-of-scope branch → 403.
    await request(server)
      .patch(`/api/v1/users/${target.body.id}`)
      .set(authHeader(scopedAdmin))
      .send({ role: 'admin', adminScope: [otherBranchId] })
      .expect(403);

    // Promote to admin within scope → ok.
    const ok = await request(server)
      .patch(`/api/v1/users/${target.body.id}`)
      .set(authHeader(scopedAdmin))
      .send({ role: 'admin', adminScope: [branchId] })
      .expect(200);
    expect(ok.body.role).toBe('admin');
  });
});

describe('Branches & Stations CRUD (Admin)', () => {
  it('creates a branch and station, audited; reads allowed to any role', async () => {
    const code = `BR${Date.now() % 100000}`;
    const branch = await request(server)
      .post('/api/v1/branches')
      .set(authHeader(admin))
      .send({ code, name: 'Jeddah South' })
      .expect(201);
    expect(branch.body.code).toBe(code);

    const station = await request(server)
      .post('/api/v1/stations')
      .set(authHeader(admin))
      .send({
        code: `ST${Date.now() % 100000}`,
        branchId: branch.body.id,
        matSizeMm: 1000,
        markerSizeMm: 100,
      })
      .expect(201);
    expect(station.body.matSizeMm).toBe(1000);

    // Reads allowed to labour (needed for display / station binding).
    await request(server).get('/api/v1/branches').set(authHeader(labour)).expect(200);
    await request(server).get('/api/v1/stations').set(authHeader(labour)).expect(200);

    // Mutations forbidden to non-admins.
    await request(server)
      .post('/api/v1/branches')
      .set(authHeader(tl))
      .send({ code: 'X', name: 'y' })
      .expect(403);

    expect(
      await prisma.auditLog.count({
        where: { entityId: branch.body.id, action: 'branch_created' },
      }),
    ).toBe(1);
    expect(
      await prisma.auditLog.count({
        where: { entityId: station.body.id, action: 'station_created' },
      }),
    ).toBe(1);
  });
});

describe('Devices (Admin)', () => {
  it('lists devices and blocks one (audited)', async () => {
    const device = await prisma.device.create({
      data: { installId: `inst-${randomUUID()}`, tier: 'standard' },
    });
    await request(server).get('/api/v1/devices').set(authHeader(admin)).expect(200);

    const res = await request(server)
      .post(`/api/v1/devices/${device.id}/block`)
      .set(authHeader(admin))
      .send({ blocked: true })
      .expect(200);
    expect(res.body.blocked).toBe(true);
    expect(
      await prisma.auditLog.count({ where: { entityId: device.id, action: 'device_blocked' } }),
    ).toBe(1);

    await request(server).get('/api/v1/devices').set(authHeader(labour)).expect(403);
  });
});

describe('Config GET/PUT (Admin, validated, audited)', () => {
  it('reads config, updates it, and validates', async () => {
    await request(server).get('/api/v1/config').set(authHeader(tl)).expect(200);

    const res = await request(server)
      .put('/api/v1/config')
      .set(authHeader(admin))
      .send({ volumetricDivisor: 6000, minDimensionCm: 2, maxDimensionCm: 250 })
      .expect(200);
    expect(res.body.volumetricDivisor).toBe(6000);
    expect(res.body.maxDimensionCm).toBe(250);
    expect(
      await prisma.auditLog.count({ where: { entity: 'config', action: 'config_updated' } }),
    ).toBeGreaterThanOrEqual(1);

    // Invalid: max < min.
    await request(server)
      .put('/api/v1/config')
      .set(authHeader(admin))
      .send({ minDimensionCm: 100, maxDimensionCm: 50 })
      .expect(400);

    // Invalid AWB regex.
    await request(server)
      .put('/api/v1/config')
      .set(authHeader(admin))
      .send({ awbRegex: '([' })
      .expect(400);

    // Forbidden to TL.
    await request(server)
      .put('/api/v1/config')
      .set(authHeader(tl))
      .send({ volumetricDivisor: 5000 })
      .expect(403);

    // Restore divisor so other suites are unaffected.
    await request(server)
      .put('/api/v1/config')
      .set(authHeader(admin))
      .send({ volumetricDivisor: 5000, minDimensionCm: 1, maxDimensionCm: 300 })
      .expect(200);
  });
});

describe('Audit read (Team Leader own branch / Admin)', () => {
  it('returns audit entries; forbids Labour', async () => {
    const res = await request(server)
      .get('/api/v1/audit?limit=5')
      .set(authHeader(admin))
      .expect(200);
    expect(Array.isArray(res.body.items)).toBe(true);
    await request(server).get('/api/v1/audit').set(authHeader(labour)).expect(403);
  });
});

describe('Reports export (Team Leader / Admin)', () => {
  it('exports daily-volume as xlsx that opens (round-trips with exceljs)', async () => {
    // Seed a package so the report has content.
    const awb = randomAwb();
    await request(server)
      .post(`/api/v1/shipments/${awb}/packages`)
      .set(authHeader(labour))
      .set('Idempotency-Key', randomUUID())
      .send(packageBody())
      .expect(201);

    const res = await request(server)
      .get('/api/v1/reports/daily-volume?format=xlsx')
      .set(authHeader(tl))
      .buffer(true)
      .parse((r, cb) => {
        const chunks: Buffer[] = [];
        r.on('data', (c: Buffer) => chunks.push(c));
        r.on('end', () => cb(null, Buffer.concat(chunks)));
      })
      .expect(200);
    expect(res.headers['content-type']).toContain('spreadsheetml');

    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(res.body as unknown as ArrayBuffer);
    const ws = wb.worksheets[0];
    expect(ws).toBeTruthy();
    expect(ws.getRow(1).getCell(1).value).toBe('Date (UTC)');

    expect(
      await prisma.auditLog.count({ where: { entity: 'report', action: 'report_exported' } }),
    ).toBeGreaterThanOrEqual(1);
  });

  it('exports productivity as csv with a header row', async () => {
    const res = await request(server)
      .get('/api/v1/reports/productivity?format=csv')
      .set(authHeader(admin))
      .buffer(true)
      .parse((r, cb) => {
        let data = '';
        r.on('data', (c: Buffer) => (data += c.toString()));
        r.on('end', () => cb(null, data));
      })
      .expect(200);
    expect(res.headers['content-type']).toContain('text/csv');
    expect(String(res.body)).toContain('Employee ID');
  });

  it('forbids Labour from reports (403)', async () => {
    await request(server).get('/api/v1/reports/flags').set(authHeader(labour)).expect(403);
  });
});

describe('Dashboard KPIs (Team Leader / Admin)', () => {
  it('returns today and range blocks; forbids Labour', async () => {
    const res = await request(server).get('/api/v1/dashboard/kpis').set(authHeader(tl)).expect(200);
    expect(res.body.today).toBeTruthy();
    expect(res.body.range).toBeTruthy();
    expect(typeof res.body.today.packages).toBe('number');
    await request(server).get('/api/v1/dashboard/kpis').set(authHeader(labour)).expect(403);
  });
});
