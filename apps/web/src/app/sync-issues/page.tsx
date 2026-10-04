'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Badge, Button, Table } from '@/components/ui';
import { Flag, listFlags, resolveFlag } from '@/lib/api';
import { StoredSession } from '@/lib/session';

/**
 * Sync issues = conflict records surfaced as flags (PRD §8, §10, §11): two
 * devices measuring the same AWB offline raise `possible_duplicate`. Resolved
 * from here like any flag.
 */
export default function SyncIssuesPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('syncIssues')} requiredRoles={['team_leader', 'admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [rows, setRows] = useState<Flag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await listFlags(token, { type: 'possible_duplicate', status: 'open' });
      setRows(res.items);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function resolve(id: string) {
    await resolveFlag(token, id, 'approve');
    load();
  }

  if (loading) return <p className="text-slate-500">{t('loading')}</p>;
  if (error) return <p className="text-red-600">{t('errorLoading')}</p>;
  if (rows.length === 0) return <p className="text-slate-500">{t('noSyncIssues')}</p>;

  return (
    <Table head={[t('filterAwb'), t('flagType'), t('note'), t('createdAt'), t('actions')]}>
      {rows.map((f) => (
        <tr key={f.id} className="border-t border-slate-100">
          <td className="px-4 py-3 font-medium">
            {f.awb ? (
              <Link
                href={`/shipments/${encodeURIComponent(f.awb)}`}
                className="text-brand hover:underline"
              >
                {f.awb}
              </Link>
            ) : (
              '—'
            )}
          </td>
          <td className="px-4 py-3">
            <Badge tone="red">{f.type}</Badge>
          </td>
          <td className="px-4 py-3 text-slate-600">{f.note ?? '—'}</td>
          <td className="px-4 py-3 text-slate-500">{new Date(f.createdAt).toLocaleString()}</td>
          <td className="px-4 py-3">
            <Button variant="primary" onClick={() => resolve(f.id)}>
              {t('resolve')}
            </Button>
          </td>
        </tr>
      ))}
    </Table>
  );
}
