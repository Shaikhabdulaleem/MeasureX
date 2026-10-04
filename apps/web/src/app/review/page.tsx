'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Badge, Button, SelectField, Table } from '@/components/ui';
import { Flag, listFlags, resolveFlag } from '@/lib/api';
import { StoredSession } from '@/lib/session';

export default function ReviewPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('reviewQueue')} requiredRoles={['team_leader', 'admin']}>
      {(session) => <ReviewBody session={session} />}
    </AppShell>
  );
}

function ReviewBody({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [flags, setFlags] = useState<Flag[]>([]);
  const [status, setStatus] = useState('open');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await listFlags(token, status ? { status } : {});
      setFlags(res.items);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [token, status]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(id: string, action: 'approve' | 'dismiss') {
    await resolveFlag(token, id, action);
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
            { value: 'resolved', label: t('resolved') },
            { value: 'dismissed', label: t('dismissed') },
            { value: '', label: t('all') },
          ]}
        />
      </div>

      {loading && <p className="text-slate-500">{t('loading')}</p>}
      {error && <p className="text-red-600">{t('errorLoading')}</p>}
      {!loading && !error && flags.length === 0 && <p className="text-slate-500">{t('noFlags')}</p>}

      {!loading && !error && flags.length > 0 && (
        <Table
          head={[
            t('filterAwb'),
            t('flagType'),
            t('status'),
            t('note'),
            t('createdAt'),
            t('actions'),
          ]}
        >
          {flags.map((f) => (
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
                <Badge tone="amber">{f.type}</Badge>
              </td>
              <td className="px-4 py-3">{f.status}</td>
              <td className="px-4 py-3 text-slate-600">{f.note ?? '—'}</td>
              <td className="px-4 py-3 text-slate-500">{new Date(f.createdAt).toLocaleString()}</td>
              <td className="px-4 py-3">
                {f.status === 'open' ? (
                  <div className="flex gap-1">
                    <Button variant="primary" onClick={() => act(f.id, 'approve')}>
                      {t('approve')}
                    </Button>
                    <Button onClick={() => act(f.id, 'dismiss')}>{t('dismiss')}</Button>
                  </div>
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
