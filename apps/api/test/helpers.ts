import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import * as argon2 from 'argon2';
import { PrismaClient, Role } from '@prisma/client';
import { AppModule } from '../src/app.module';

export const TEST_PASSWORD = 'InitPass123!';
export const TEST_BRANCH_CODE = 'TST';

export async function buildApp(): Promise<INestApplication> {
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
  const app = moduleRef.createNestApplication();
  app.setGlobalPrefix('api/v1');
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }),
  );
  await app.init();
  return app;
}

export async function ensureBranch(prisma: PrismaClient): Promise<string> {
  const branch = await prisma.branch.upsert({
    where: { code: TEST_BRANCH_CODE },
    update: {},
    create: { code: TEST_BRANCH_CODE, name: 'Test Branch', status: 'active' },
  });
  return branch.id;
}

export interface SeedUserOptions {
  employeeId: string;
  role?: Role;
  mustChangePassword?: boolean;
  password?: string;
  adminScope?: unknown;
}

export async function createUser(
  prisma: PrismaClient,
  branchId: string,
  opts: SeedUserOptions,
): Promise<string> {
  const passwordHash = await argon2.hash(opts.password ?? TEST_PASSWORD);
  // Clean any prior run for this employeeId (and its sessions/audit).
  const existing = await prisma.user.findUnique({ where: { employeeId: opts.employeeId } });
  if (existing) {
    await prisma.session.deleteMany({ where: { userId: existing.id } });
    await prisma.auditLog.deleteMany({ where: { entityId: existing.id } });
    await prisma.user.delete({ where: { id: existing.id } });
  }
  const user = await prisma.user.create({
    data: {
      employeeId: opts.employeeId,
      name: opts.employeeId,
      role: opts.role ?? Role.labour,
      homeBranchId: branchId,
      adminScope: opts.adminScope === undefined ? undefined : (opts.adminScope as object),
      passwordHash,
      mustChangePassword: opts.mustChangePassword ?? false,
      status: 'active',
    },
  });
  return user.id;
}

/** Create (or reuse) a branch by code; returns its id. */
export async function createBranch(prisma: PrismaClient, code: string): Promise<string> {
  const branch = await prisma.branch.upsert({
    where: { code },
    update: {},
    create: { code, name: `Branch ${code}`, status: 'active' },
  });
  return branch.id;
}

type Server = ReturnType<INestApplication['getHttpServer']>;

export interface AuthContext {
  userId: string;
  accessToken: string;
  refreshToken: string;
}

/** Log a seeded user in and return their tokens (for authenticated requests). */
export async function loginAs(
  server: Server,
  employeeId: string,
  password: string = TEST_PASSWORD,
): Promise<{ accessToken: string; refreshToken: string }> {
  const res = await request(server)
    .post('/api/v1/auth/login')
    .send({ employeeId, password })
    .expect(200);
  return { accessToken: res.body.accessToken, refreshToken: res.body.refreshToken };
}

/** Create a user in a branch and log them in, returning id + tokens. */
export async function createAndLogin(
  prisma: PrismaClient,
  server: Server,
  branchId: string,
  opts: SeedUserOptions,
): Promise<AuthContext> {
  const userId = await createUser(prisma, branchId, opts);
  const { accessToken, refreshToken } = await loginAs(
    server,
    opts.employeeId,
    opts.password ?? TEST_PASSWORD,
  );
  return { userId, accessToken, refreshToken };
}

/** A unique employee id per run so cleanup never collides with prior packages. */
export function uniqueEmployeeId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
}

/** A fresh valid AWB (`AY` + 11 digits) so repeated test runs never collide. */
export function randomAwb(): string {
  let digits = '';
  for (let i = 0; i < 11; i++) digits += Math.floor(Math.random() * 10);
  return `AY${digits}`;
}
