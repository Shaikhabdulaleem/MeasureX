'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useI18n } from '@/i18n/client';
import { LanguageToggle } from '@/components/LanguageToggle';
import { logout } from '@/lib/api';
import { clearSession, getSession, StoredSession } from '@/lib/session';

const ROLE_LABELS: Record<string, string> = {
  labour: 'roleLabour',
  team_leader: 'roleTeamLeader',
  admin: 'roleAdmin',
};

export default function DashboardPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [session, setSession] = useState<StoredSession | null>(null);

  useEffect(() => {
    const s = getSession();
    if (!s) router.replace('/login');
    else if (s.user.mustChangePassword) router.replace('/change-password');
    else setSession(s);
  }, [router]);

  async function onSignOut() {
    const s = getSession();
    if (s) await logout(s.accessToken, s.refreshToken);
    clearSession();
    router.replace('/login');
  }

  if (!session) return null;

  return (
    <main className="min-h-screen">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-lg font-bold text-brand">{t('appName')}</h1>
        <div className="flex items-center gap-3">
          <LanguageToggle />
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            {t('signOut')}
          </button>
        </div>
      </header>

      <section className="mx-auto max-w-3xl p-6">
        <h2 className="text-2xl font-bold text-slate-900">{t('dashboard')}</h2>
        <div className="mt-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <p className="text-slate-700">
            {t('welcome')}, <span className="font-semibold">{session.user.name}</span>
          </p>
          <p className="mt-1 text-sm text-slate-500">
            {t('employeeId')}: {session.user.employeeId}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            {t('role')}: {t(ROLE_LABELS[session.user.role] ?? session.user.role)}
          </p>
        </div>
        <div className="mt-6">
          <Link
            href="/shipments"
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-3 font-semibold text-white hover:opacity-90"
          >
            {t('shipments')} →
          </Link>
        </div>

        <p className="mt-6 text-sm text-slate-400">{t('dashboardEmpty')}</p>
      </section>
    </main>
  );
}
