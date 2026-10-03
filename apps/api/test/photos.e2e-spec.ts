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

const WORKED = { lengthMm: 452, widthMm: 301, heightMm: 204 };

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  await prisma.config.upsert({
    where: { key: 'actual_weight_required' },
    update: { value: false },
    create: { key: 'actual_weight_required', value: false, scope: 'global' },
  });
  const branchId = await createBranch(prisma, 'PHO');
  labour = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('PHO_LAB'),
    role: 'labour',
  });
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

async function createPackage(awb: string): Promise<string> {
  const res = await request(server)
    .post(`/api/v1/shipments/${awb}/packages`)
    .set('Authorization', `Bearer ${labour.accessToken}`)
    .set('Idempotency-Key', randomUUID())
    .send({
      id: randomUUID(),
      ...WORKED,
      method: 'manual',
      weightSource: 'none',
      confirmedAt: new Date().toISOString(),
    })
    .expect(201);
  return res.body.id;
}

describe('Photo upload URL refresh (retry path)', () => {
  it('reuses the same photo row and returns a fresh signed URL', async () => {
    const packageId = await createPackage(randomAwb());

    // First request: creates the photo row and returns the initial URL.
    const first = await request(server)
      .post(`/api/v1/packages/${packageId}/photos`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .send({ kind: 'raw', contentType: 'image/jpeg', bytes: 1000 })
      .expect(201);
    const photoId = first.body.photoId as string;
    expect(first.body.uploadUrl).toContain('http');

    // Retry: a fresh URL for the SAME photo, no new row.
    const refreshed = await request(server)
      .post(`/api/v1/photos/${photoId}/upload-url`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(200);
    expect(refreshed.body.photoId).toBe(photoId);
    expect(refreshed.body.uploadUrl).toContain('http');

    const count = await prisma.photo.count({ where: { packageId, deletedAt: null } });
    expect(count).toBe(1);
  });

  it('404s for an unknown photo id', async () => {
    await request(server)
      .post(`/api/v1/photos/${randomUUID()}/upload-url`)
      .set('Authorization', `Bearer ${labour.accessToken}`)
      .expect(404);
  });
});
