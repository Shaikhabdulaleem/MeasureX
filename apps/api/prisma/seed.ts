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
  // Scale lands in M2; actual weight is not required to save in M1 (PRD A6, M1 scope).
  { key: 'actual_weight_required', value: false },
  { key: 'medium_confirm_allowed', value: true },
  { key: 'min_dimension_cm', value: 1 },
  { key: 'max_dimension_cm', value: 300 },
  { key: 'idle_auto_complete_minutes', value: 30 },
  { key: 'photo_retention_months', value: 12 },
  { key: 'local_purge_days', value: 7 },
];

async function main(): Promise<void> {
  const branch = await prisma.branch.upsert({
    where: { code: 'RUH' },
    update: {},
    create: { code: 'RUH', name: 'Riyadh', status: 'active' },
  });

  const passwordHash = await argon2.hash(INITIAL_PASSWORD);

  for (const u of USERS) {
    await prisma.user.upsert({
      where: { employeeId: u.employeeId },
      update: {},
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
