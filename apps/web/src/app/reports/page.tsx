'use client';

import { useState } from 'react';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Button, Card, SelectField, TextField } from '@/components/ui';
import { downloadReport } from '@/lib/api';
import { StoredSession } from '@/lib/session';

const TYPES = [
  { value: 'daily-volume', key: 'reportDailyVolume' },
  { value: 'productivity', key: 'reportProductivity' },
  { value: 'flags', key: 'reportFlags' },
  { value: 'manual-entry-rate', key: 'reportManualRate' },
];

export default function ReportsPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('reports')} requiredRoles={['team_leader', 'admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [type, setType] = useState('daily-volume');
  const [format, setFormat] = useState<'xlsx' | 'csv'>('xlsx');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function run() {
    setBusy(true);
    setError(false);
    try {
      await downloadReport(token, type, format, {
        dateFrom: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        dateTo: dateTo ? new Date(dateTo).toISOString() : undefined,
      });
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-2xl">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SelectField
          label={t('reportType')}
          value={type}
          onChange={setType}
          options={TYPES.map((x) => ({ value: x.value, label: t(x.key) }))}
        />
        <SelectField
          label={t('format')}
          value={format}
          onChange={(v) => setFormat(v as 'xlsx' | 'csv')}
          options={[
            { value: 'xlsx', label: 'Excel (.xlsx)' },
            { value: 'csv', label: 'CSV (.csv)' },
          ]}
        />
        <TextField
          label={t('filterDateFrom')}
          type="date"
          value={dateFrom}
          onChange={setDateFrom}
        />
        <TextField label={t('filterDateTo')} type="date" value={dateTo} onChange={setDateTo} />
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{t('actionFailed')}</p>}
      <div className="mt-5">
        <Button variant="primary" onClick={run} disabled={busy}>
          {busy ? t('exporting') : t('download')}
        </Button>
      </div>
    </Card>
  );
}
