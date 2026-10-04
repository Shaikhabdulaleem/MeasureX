'use client';

import { ReactNode, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useI18n } from '@/i18n/client';
import { LanguageToggle } from '@/components/LanguageToggle';
import { logout } from '@/lib/api';
import { clearSession, getSession, StoredSession } from '@/lib/session';

type Role = 'labour' | 'team_leader' | 'admin';

interface NavItem {
  href: string;
  key: string;
  roles: Role[];
}

const NAV: NavItem[] = [
  { href: '/dashboard', key: 'navDashboard', roles: ['team_leader', 'admin'] },
  { href: '/shipments', key: 'navShipments', roles: ['labour', 'team_leader', 'admin'] },
  { href: '/review', key: 'navReview', roles: ['team_leader', 'admin'] },
  { href: '/remeasurements', key: 'navRemeasurements', roles: ['team_leader', 'admin'] },
  { href: '/sync-issues', key: 'navSyncIssues', roles: ['team_leader', 'admin'] },
  { href: '/reports', key: 'navReports', roles: ['team_leader', 'admin'] },
  { href: '/audit', key: 'navAudit', roles: ['team_leader', 'admin'] },
  { href: '/users', key: 'navUsers', roles: ['admin'] },
  { href: '/branches', key: 'navBranches', roles: ['admin'] },
  { href: '/stations', key: 'navStations', roles: ['admin'] },
  { href: '/devices', key: 'navDevices', roles: ['admin'] },
  { href: '/config', key: 'navConfig', roles: ['admin'] },
];

/**
 * Shared authenticated layout: enforces a client-side session guard and
 * role-gated navigation (server-side scope is still enforced by the API).
 * `requiredRoles`, when set, blocks the page for other roles.
 */
export function AppShell({
  title,
  children,
  requiredRoles,
}: {
  title: string;
  children: (session: StoredSession) => ReactNode;
  requiredRoles?: Role[];
}) {
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<StoredSession | null>(null);

  useEffect(() => {
    const s = getSession();
    if (!s) {
      router.replace('/login');
      return;
    }
    if (s.user.mustChangePassword) {
      router.replace('/change-password');
      return;
    }
    setSession(s);
  }, [router]);

  async function onSignOut() {
    const s = getSession();
    if (s) await logout(s.accessToken, s.refreshToken);
    clearSession();
    router.replace('/login');
  }

  if (!session) return null;

  const role = session.user.role as Role;
  if (requiredRoles && !requiredRoles.includes(role)) {
    return <Blocked onSignOut={onSignOut} message={t('notAuthorised')} back={t('navDashboard')} />;
  }

  const items = NAV.filter((n) => n.roles.includes(role));

  return (
    <main className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-lg font-bold text-brand">
              {t('appName')}
            </Link>
            <span className="text-slate-300">/</span>
            <h1 className="text-base font-semibold text-slate-800">{title}</h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-500 sm:inline">{session.user.name}</span>
            <LanguageToggle />
            <button
              type="button"
              onClick={onSignOut}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              {t('signOut')}
            </button>
          </div>
        </div>
        <nav className="flex flex-wrap gap-1 px-4 pb-2">
          {items.map((n) => {
            const active = pathname === n.href || pathname.startsWith(n.href + '/');
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  active ? 'bg-brand text-white' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {t(n.key)}
              </Link>
            );
          })}
        </nav>
      </header>
      <section className="mx-auto max-w-6xl p-6">{children(session)}</section>
    </main>
  );
}

function Blocked({
  onSignOut,
  message,
  back,
}: {
  onSignOut: () => void;
  message: string;
  back: string;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-lg font-semibold text-slate-800">{message}</p>
      <div className="flex gap-3">
        <Link
          href="/dashboard"
          className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white"
        >
          {back}
        </Link>
        <button
          type="button"
          onClick={onSignOut}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
        >
          Sign out
        </button>
      </div>
    </main>
  );
}
