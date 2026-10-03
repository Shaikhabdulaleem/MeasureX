/**
 * Seed data for Milestone 0.
 *
 * Creates one branch, four users (admin, team leader, two labour) and the
 * default configuration. All users start with must_change_password = true, so
 * the first login forces a password change (PRD §3).
 *
 * TEST credentials for local development only — every seeded user shares the
 * initial password below and must change it on first login.
 */
import { PrismaClient, Role } from '@prisma/client';
import * as argon2 from 'argon2';

const prisma = new PrismaClient();

const INITIAL_PASSWORD = 'ChangeMe123!';

const USERS: Array<{ employeeId: string; name: string; role: Role; adminScope?: unknown }> = [
  { employeeId: 'ADMIN001', name: 'Ops Admin', role: Role.admin, adminScope: 'all' },
  { employeeId: 'TL001', name: 'Team Leader One', role: Role.team_leader },
  { employeeId: 'LAB001', name: 'Labour One', role: Role.labour },
  { employeeId: 'LAB002', name: 'Labour Two', role: Role.labour },
];

const CONFIG: Array<{ key: string; value: unknown }> = [
  { key: 'awb_regex', value: '^AY\\d{11}$' },
  { key: 'volumetric_divisor', value: 5000 },
  { key: 'chargeable_step_kg', value: 0.5 },
  // Actual weight required to save by default (PRD A6); scale capture lands in M2.
  { key: 'actual_weight_required', value: true },
  { key: 'medium_confirm_allowed', value: true },
  { key: 'min_dimension_cm', value: 1 },
  { key: 'max_dimension_cm', value: 300 },
  { key: 'idle_auto_complete_minutes', value: 30 },
  { key: 'photo_retention_months', value: 12 },
  { key: 'local_purge_days', value: 7 },
];

async function main(): Promise<void> {
  const nodeEnv = process.env.NODE_ENV ?? 'development';
  // Never seed a production database: it carries test users with a shared
  // password and (below) a dev-only simulated scale.
  if (nodeEnv === 'production') {
    throw new Error('Refusing to run the seed with NODE_ENV=production');
  }
  const isDevOrTest = nodeEnv === 'development' || nodeEnv === 'test';

  const branch = await prisma.branch.upsert({
    where: { code: 'RUH' },
    update: {},
    create: { code: 'RUH', name: 'Riyadh', status: 'active' },
  });

  const passwordHash = await argon2.hash(INITIAL_PASSWORD);

  for (const u of USERS) {
    await prisma.user.upsert({
      where: { employeeId: u.employeeId },
      // Keep the admin scope correct on re-seed: an admin with no scope now has
      // NO access (fail-closed), so ADMIN001 must stay explicitly "all".
      update: { adminScope: u.adminScope === undefined ? undefined : (u.adminScope as object) },
      create: {
        employeeId: u.employeeId,
        name: u.name,
        role: u.role,
        homeBranchId: branch.id,
        adminScope: u.adminScope === undefined ? undefined : (u.adminScope as object),
        passwordHash,
        mustChangePassword: true,
        status: 'active',
      },
    });
  }

  for (const c of CONFIG) {
    await prisma.config.upsert({
      where: { key: c.key },
      update: { value: c.value as object },
      create: { key: c.key, value: c.value as object, scope: 'global' },
    });
  }

  // DEV/TEST ONLY: an approved "simulated" scale so the M2 scale flow can be
  // exercised end-to-end without hardware (the simulated adapter is dev-only).
  // Real scale models are added by an Admin once chosen (PRD §9, Q6).
  if (isDevOrTest) {
    const existingSim = await prisma.scale.findFirst({
      where: { adapterKey: 'simulated', deletedAt: null },
    });
    if (!existingSim) {
      await prisma.scale.create({
        data: {
          model: 'Simulated Scale (dev)',
          connection: 'hid',
          adapterKey: 'simulated',
          approved: true,
          streaming: true, // the simulated adapter emits a settling stream
        },
      });
    }
  }

  // eslint-disable-next-line no-console
  console.log(
    `Seeded branch ${branch.code}, ${USERS.length} users (initial password "${INITIAL_PASSWORD}"), ${CONFIG.length} config rows.`,
  );
}

main()
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => {
    void prisma.$disconnect();
  });
