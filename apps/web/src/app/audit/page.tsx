'use client';

import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Button, Modal, Table, TextField } from '@/components/ui';
import { AuditRow, listAudit } from '@/lib/api';
import { StoredSession } from '@/lib/session';

export default function AuditPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('auditLog')} requiredRoles={['team_leader', 'admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [entity, setEntity] = useState('');
  const [action, setAction] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [detail, setDetail] = useState<AuditRow | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await listAudit(token, {
        entity: entity || undefined,
        action: action || undefined,
      });
      setRows(res.items);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [token, entity, action]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <form
        className="mb-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
      >
        <TextField
          label={t('entity')}
          value={entity}
          onChange={setEntity}
          placeholder="package, shipment, user…"
        />
        <TextField
          label={t('action')}
          value={action}
          onChange={setAction}
          placeholder="package_corrected…"
        />
        <Button type="submit" variant="primary">
          {t('apply')}
        </Button>
      </form>

      {loading && <p className="text-slate-500">{t('loading')}</p>}
      {error && <p className="text-red-600">{t('errorLoading')}</p>}
      {!loading && !error && rows.length === 0 && <p className="text-slate-500">{t('noAudit')}</p>}

      {!loading && !error && rows.length > 0 && (
        <Table head={[t('time'), t('entity'), t('action'), t('reason'), '']}>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-slate-100">
              <td className="px-4 py-3 text-slate-500">{new Date(r.at).toLocaleString()}</td>
              <td className="px-4 py-3">{r.entity}</td>
              <td className="px-4 py-3 font-medium">{r.action}</td>
              <td className="px-4 py-3 text-slate-600">{r.reason ?? '—'}</td>
              <td className="px-4 py-3">
                {Boolean(r.before || r.after) && (
                  <Button onClick={() => setDetail(r)}>{t('viewChange')}</Button>
                )}
              </td>
            </tr>
          ))}
        </Table>
      )}

      {detail && (
        <Modal title={detail.action} onClose={() => setDetail(null)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-sm font-semibold text-slate-500">{t('before')}</p>
              <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
                {JSON.stringify(detail.before ?? null, null, 2)}
              </pre>
            </div>
            <div>
              <p className="mb-1 text-sm font-semibold text-slate-500">{t('after')}</p>
              <pre className="overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
                {JSON.stringify(detail.after ?? null, null, 2)}
              </pre>
            </div>
          </div>
          <div className="mt-6 flex justify-end">
            <Button onClick={() => setDetail(null)}>{t('close')}</Button>
          </div>
        </Modal>
      )}
    </>
  );
}
