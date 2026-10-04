'use client';

import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Badge, Button, Table } from '@/components/ui';
import { blockDevice, Device, listDevices } from '@/lib/api';
import { StoredSession } from '@/lib/session';

export default function DevicesPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('devices')} requiredRoles={['admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [rows, setRows] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await listDevices(token);
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

  if (loading) return <p className="text-slate-500">{t('loading')}</p>;
  if (error) return <p className="text-red-600">{t('errorLoading')}</p>;

  return (
    <Table head={[t('name'), t('tier'), t('lastSeen'), t('status'), t('actions')]}>
      {rows.map((d) => (
        <tr key={d.id} className="border-t border-slate-100">
          <td className="px-4 py-3 font-medium">
            {[d.manufacturer, d.model].filter(Boolean).join(' ') || d.installId.slice(0, 12)}
            <span className="block text-xs text-slate-400">
              {d.os} {d.osVersion}
            </span>
          </td>
          <td className="px-4 py-3">{d.tier}</td>
          <td className="px-4 py-3 text-slate-500">
            {d.lastSeenAt ? new Date(d.lastSeenAt).toLocaleString() : '—'}
          </td>
          <td className="px-4 py-3">
            {d.blocked ? (
              <Badge tone="red">{t('blocked')}</Badge>
            ) : (
              <Badge tone="green">{t('active')}</Badge>
            )}
          </td>
          <td className="px-4 py-3">
            <Button
              variant={d.blocked ? 'secondary' : 'danger'}
              onClick={async () => {
                await blockDevice(token, d.id, !d.blocked);
                load();
              }}
            >
              {d.blocked ? t('unblock') : t('block')}
            </Button>
          </td>
        </tr>
      ))}
    </Table>
  );
}
