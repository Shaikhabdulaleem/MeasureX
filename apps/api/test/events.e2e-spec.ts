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

function event(extra: Record<string, unknown> = {}) {
  return {
    id: randomUUID(),
    type: 'scan',
    occurredAt: new Date().toISOString(),
    ...extra,
  };
}

function postEvents(events: Array<Record<string, unknown>>) {
  return request(server)
    .post('/api/v1/events/batch')
    .set('Authorization', `Bearer ${labour.accessToken}`)
    .send({ events });
}

beforeAll(async () => {
  app = await buildApp();
  server = app.getHttpServer();
  const branchId = await createBranch(prisma, 'EVT');
  labour = await createAndLogin(prisma, server, branchId, {
    employeeId: uniqueEmployeeId('EVT_LAB'),
    role: 'labour',
  });
});

afterAll(async () => {
  await app.close();
  await prisma.$disconnect();
});

describe('POST /events/batch', () => {
  it('accepts a batch of telemetry (202) and stores the rows', async () => {
    const awb = randomAwb();
    const e1 = event({ awb, type: 'measure_ready', payload: { ms: 1800 } });
    const e2 = event({ awb, type: 'confirm' });

    const res = await postEvents([e1, e2]).expect(202);
    expect(res.body.inserted).toBe(2);

    const stored = await prisma.measurementEvent.findMany({ where: { awb } });
    expect(stored).toHaveLength(2);
  });

  it('is replay-safe: resending the same ids inserts nothing new', async () => {
    const awb = randomAwb();
    const batch = [event({ awb }), event({ awb })];

    const first = await postEvents(batch).expect(202);
    expect(first.body.inserted).toBe(2);

    const replay = await postEvents(batch).expect(202);
    expect(replay.body.inserted).toBe(0);

    const stored = await prisma.measurementEvent.findMany({ where: { awb } });
    expect(stored).toHaveLength(2);
  });
});
