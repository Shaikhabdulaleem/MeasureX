'use client';

import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Badge, Button, Modal, Table, TextField } from '@/components/ui';
import { Branch, createBranch, listBranches, updateBranch } from '@/lib/api';
import { StoredSession } from '@/lib/session';

export default function BranchesPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('branches')} requiredRoles={['admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [rows, setRows] = useState<Branch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await listBranches(token);
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

  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button variant="primary" onClick={() => setShowCreate(true)}>
          {t('add')}
        </Button>
      </div>

      {loading && <p className="text-slate-500">{t('loading')}</p>}
      {error && <p className="text-red-600">{t('errorLoading')}</p>}

      {!loading && !error && (
        <Table head={[t('code'), t('name'), t('status'), t('actions')]}>
          {rows.map((b) => (
            <tr key={b.id} className="border-t border-slate-100">
              <td className="px-4 py-3 font-medium">{b.code}</td>
              <td className="px-4 py-3">{b.name}</td>
              <td className="px-4 py-3">
                <Badge tone={b.status === 'active' ? 'green' : 'slate'}>{b.status}</Badge>
              </td>
              <td className="px-4 py-3">
                <Button
                  onClick={async () => {
                    await updateBranch(token, b.id, {
                      status: b.status === 'active' ? 'inactive' : 'active',
                    });
                    load();
                  }}
                >
                  {b.status === 'active' ? t('inactive') : t('active')}
                </Button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {showCreate && (
        <CreateModal
          token={token}
          onClose={() => setShowCreate(false)}
          onDone={() => {
            setShowCreate(false);
            load();
          }}
        />
      )}
    </>
  );
}

function CreateModal({
  token,
  onClose,
  onDone,
}: {
  token: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!code.trim() || !name.trim()) {
      setErr(t('reasonRequired'));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await createBranch(token, { code, name });
      onDone();
    } catch {
      setErr(t('actionFailed'));
      setBusy(false);
    }
  }

  return (
    <Modal title={t('create')} onClose={onClose}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField label={t('code')} value={code} onChange={setCode} />
        <TextField label={t('name')} value={name} onChange={setName} />
      </div>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onClose}>{t('cancel')}</Button>
        <Button variant="primary" onClick={submit} disabled={busy}>
          {busy ? t('saving') : t('create')}
        </Button>
      </div>
    </Modal>
  );
}
