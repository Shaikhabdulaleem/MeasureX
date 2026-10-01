import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { buildApp, createUser, ensureBranch, TEST_PASSWORD } from './helpers';

const prisma = new PrismaClient();
let app: INestApplication;
let branchId: string;
let server: ReturnType<INestApplication['getHttpServer']>;

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  branchId = await ensureBranch(prisma);
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

describe('GET /health', () => {
  it('returns ok with the db up', async () => {
    const res = await request(server).get('/api/v1/health').expect(200);
    expect(res.body.status).toBe('ok');
    expect(res.body.db).toBe('up');
  });
});

describe('POST /auth/login', () => {
  it('logs in a valid user and writes an audit entry', async () => {
    const userId = await createUser(prisma, branchId, { employeeId: 'E2E_LOGIN' });
    const res = await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_LOGIN', password: TEST_PASSWORD })
      .expect(200);

    expect(res.body.accessToken).toBeTruthy();
    expect(res.body.refreshToken).toBeTruthy();
    expect(res.body.user.employeeId).toBe('E2E_LOGIN');

    const audit = await prisma.auditLog.findFirst({
      where: { entityId: userId, action: 'login_success' },
    });
    expect(audit).not.toBeNull();
  });

  it('rejects a wrong password with 401', async () => {
    await createUser(prisma, branchId, { employeeId: 'E2E_BADPW' });
    await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_BADPW', password: 'wrong-password' })
      .expect(401);
  });

  it('locks the account for 15 minutes after 5 failed attempts', async () => {
    const userId = await createUser(prisma, branchId, { employeeId: 'E2E_LOCK' });
    for (let i = 0; i < 5; i++) {
      await request(server)
        .post('/api/v1/auth/login')
        .send({ employeeId: 'E2E_LOCK', password: 'nope' })
        .expect(401);
    }
    // Even the correct password is now locked out (423).
    const res = await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_LOCK', password: TEST_PASSWORD })
      .expect(423);
    expect(res.body.code).toBe('ACCOUNT_LOCKED');

    const user = await prisma.user.findUnique({ where: { id: userId } });
    expect(user?.lockedUntil).toBeTruthy();
    const minutesAhead = (user!.lockedUntil!.getTime() - Date.now()) / 60000;
    expect(minutesAhead).toBeGreaterThan(14);
    expect(minutesAhead).toBeLessThanOrEqual(15);
  });
});

describe('Forced password change on first login', () => {
  it('flags the first login and clears it after change-password', async () => {
    await createUser(prisma, branchId, {
      employeeId: 'E2E_FORCE',
      mustChangePassword: true,
    });

    const first = await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_FORCE', password: TEST_PASSWORD })
      .expect(200);
    expect(first.body.mustChangePassword).toBe(true);

    await request(server)
      .post('/api/v1/auth/change-password')
      .set('Authorization', `Bearer ${first.body.accessToken}`)
      .send({ currentPassword: TEST_PASSWORD, newPassword: 'BrandNew123!' })
      .expect(204);

    const second = await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_FORCE', password: 'BrandNew123!' })
      .expect(200);
    expect(second.body.mustChangePassword).toBe(false);

    // Old password no longer works.
    await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_FORCE', password: TEST_PASSWORD })
      .expect(401);
  });

  it('rejects change-password with a wrong current password', async () => {
    await createUser(prisma, branchId, { employeeId: 'E2E_CHGBAD', mustChangePassword: true });
    const login = await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_CHGBAD', password: TEST_PASSWORD })
      .expect(200);
    const res = await request(server)
      .post('/api/v1/auth/change-password')
      .set('Authorization', `Bearer ${login.body.accessToken}`)
      .send({ currentPassword: 'not-it', newPassword: 'Whatever123!' })
      .expect(400);
    expect(res.body.code).toBe('INVALID_CURRENT_PASSWORD');
  });
});

describe('Refresh and logout', () => {
  it('rotates refresh tokens and invalidates the used one', async () => {
    await createUser(prisma, branchId, { employeeId: 'E2E_REFRESH' });
    const login = await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_REFRESH', password: TEST_PASSWORD })
      .expect(200);

    const refreshed = await request(server)
      .post('/api/v1/auth/refresh')
      .send({ refreshToken: login.body.refreshToken })
      .expect(200);
    expect(refreshed.body.accessToken).toBeTruthy();

    // The original refresh token is now revoked.
    await request(server)
      .post('/api/v1/auth/refresh')
      .send({ refreshToken: login.body.refreshToken })
      .expect(401);
  });

  it('revokes the session on logout', async () => {
    await createUser(prisma, branchId, { employeeId: 'E2E_LOGOUT' });
    const login = await request(server)
      .post('/api/v1/auth/login')
      .send({ employeeId: 'E2E_LOGOUT', password: TEST_PASSWORD })
      .expect(200);

    await request(server)
      .post('/api/v1/auth/logout')
      .set('Authorization', `Bearer ${login.body.accessToken}`)
      .send({ refreshToken: login.body.refreshToken })
      .expect(204);

    await request(server)
      .post('/api/v1/auth/refresh')
      .send({ refreshToken: login.body.refreshToken })
      .expect(401);
  });
});

describe('Authentication required', () => {
  it('rejects change-password without a token', async () => {
    await request(server)
      .post('/api/v1/auth/change-password')
      .send({ currentPassword: 'x', newPassword: 'yyyyyyyy' })
      .expect(401);
  });
});
