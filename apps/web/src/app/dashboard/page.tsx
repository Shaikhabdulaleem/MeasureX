'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Card } from '@/components/ui';
import { getKpis, Kpis } from '@/lib/api';
import { getSession } from '@/lib/session';

const kg1 = (g: number) => `${(g / 1000).toFixed(1)} kg`;
const pct = (r: number) => `${(r * 100).toFixed(0)}%`;

export default function DashboardPage() {
  const { t } = useI18n();

  return (
    <AppShell title={t('navDashboard')} requiredRoles={['team_leader', 'admin']}>
      {() => <DashboardBody />}
    </AppShell>
  );
}

function DashboardBody() {
  const { t } = useI18n();
  const [data, setData] = useState<{ today: Kpis; range: Kpis } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const s = getSession();
    if (!s) return;
    getKpis(s.accessToken)
      .then(setData)
      .catch(() => setError(true));
  }, []);

  if (error) return <p className="text-red-600">{t('errorLoading')}</p>;
  if (!data) return <p className="text-slate-500">{t('loading')}</p>;

  return (
    <div className="space-y-8">
      <KpiBlock title={t('kpiToday')} k={data.today} />
      <KpiBlock title={t('kpiRange')} k={data.range} />
    </div>
  );

  function KpiBlock({ title, k }: { title: string; k: Kpis }) {
    const tiles: { label: string; value: string; href?: string }[] = [
      { label: t('kpiShipments'), value: String(k.shipments) },
      { label: t('kpiPackages'), value: String(k.packages) },
      { label: t('cbm'), value: k.cbm.toFixed(3) },
      { label: t('kpiChargeable'), value: kg1(k.chargeableG) },
      { label: t('kpiManualRate'), value: pct(k.manualEntryRate) },
      { label: t('kpiRetakeRate'), value: pct(k.retakeRate) },
      { label: t('kpiFlagsOpen'), value: String(k.flagsOpen), href: '/review' },
      { label: t('kpiRemeasuresOpen'), value: String(k.remeasuresOpen), href: '/remeasurements' },
    ];
    return (
      <div>
        <h2 className="mb-3 text-lg font-bold text-slate-800">{title}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {tiles.map((tile) => {
            const body = (
              <Card className="h-full">
                <p className="text-xs uppercase tracking-wide text-slate-400">{tile.label}</p>
                <p className="mt-1 text-2xl font-bold text-slate-900">{tile.value}</p>
              </Card>
            );
            return tile.href ? (
              <Link key={tile.label} href={tile.href} className="block transition hover:opacity-80">
                {body}
              </Link>
            ) : (
              <div key={tile.label}>{body}</div>
            );
          })}
        </div>
      </div>
    );
  }
}
