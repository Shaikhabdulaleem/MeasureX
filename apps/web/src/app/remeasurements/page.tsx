'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Badge, Button, SelectField, Table } from '@/components/ui';
import { cancelRemeasure, listRemeasurements, RemeasureRequestRow } from '@/lib/api';
import { StoredSession } from '@/lib/session';

function ageText(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

export default function RemeasurementsPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('navRemeasurements')} requiredRoles={['team_leader', 'admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [rows, setRows] = useState<RemeasureRequestRow[]>([]);
  const [status, setStatus] = useState('open');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await listRemeasurements(token, status || undefined);
      setRows(res.items);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [token, status]);

  useEffect(() => {
    load();
  }, [load]);

  async function cancel(id: string) {
    await cancelRemeasure(token, id);
    load();
  }

  return (
    <>
      <div className="mb-4 max-w-xs">
        <SelectField
          label={t('status')}
          value={status}
          onChange={setStatus}
          options={[
            { value: 'open', label: t('open') },
            { value: 'done', label: t('resolved') },
            { value: 'cancelled', label: t('dismissed') },
            { value: '', label: t('all') },
          ]}
        />
      </div>

      {loading && <p className="text-slate-500">{t('loading')}</p>}
      {error && <p className="text-red-600">{t('errorLoading')}</p>}
      {!loading && !error && rows.length === 0 && (
        <p className="text-slate-500">{t('noRemeasurements')}</p>
      )}

      {!loading && !error && rows.length > 0 && (
        <Table head={[t('filterAwb'), t('reason'), t('status'), t('age'), t('note'), t('actions')]}>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-slate-100">
              <td className="px-4 py-3 font-medium">
                {r.awb ? (
                  <Link
                    href={`/shipments/${encodeURIComponent(r.awb)}`}
                    className="text-brand hover:underline"
                  >
                    {r.awb}
                  </Link>
                ) : (
                  '—'
                )}
              </td>
              <td className="px-4 py-3">{r.reason}</td>
              <td className="px-4 py-3">
                <Badge
                  tone={r.status === 'open' ? 'amber' : r.status === 'done' ? 'green' : 'slate'}
                >
                  {r.status}
                </Badge>
              </td>
              <td className="px-4 py-3 text-slate-500">{ageText(r.createdAt)}</td>
              <td className="px-4 py-3 text-slate-600">{r.note ?? '—'}</td>
              <td className="px-4 py-3">
                {r.status === 'open' ? (
                  <Button variant="danger" onClick={() => cancel(r.id)}>
                    {t('cancel')}
                  </Button>
                ) : (
                  '—'
                )}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
