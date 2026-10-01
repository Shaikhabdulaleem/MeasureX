import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
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
      passwordHash,
      mustChangePassword: opts.mustChangePassword ?? false,
      status: 'active',
    },
  });
  return user.id;
}
