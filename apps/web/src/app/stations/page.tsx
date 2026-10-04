'use client';

import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Button, Modal, SelectField, Table, TextField } from '@/components/ui';
import { Branch, createStation, listBranches, listStations, Station } from '@/lib/api';
import { StoredSession } from '@/lib/session';

export default function StationsPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('stations')} requiredRoles={['admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [rows, setRows] = useState<Station[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [s, b] = await Promise.all([listStations(token), listBranches(token)]);
      setRows(s.items);
      setBranches(b.items);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const branchName = (id: string) => branches.find((b) => b.id === id)?.code ?? id.slice(0, 8);

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
        <Table head={[t('code'), t('filterBranch'), t('matSize'), t('markerSize')]}>
          {rows.map((s) => (
            <tr key={s.id} className="border-t border-slate-100">
              <td className="px-4 py-3 font-medium">{s.code}</td>
              <td className="px-4 py-3">{branchName(s.branchId)}</td>
              <td className="px-4 py-3">{s.matSizeMm}</td>
              <td className="px-4 py-3">{s.markerSizeMm}</td>
            </tr>
          ))}
        </Table>
      )}

      {showCreate && (
        <CreateModal
          token={token}
          branches={branches}
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
  branches,
  onClose,
  onDone,
}: {
  token: string;
  branches: Branch[];
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [code, setCode] = useState('');
  const [branchId, setBranchId] = useState(branches[0]?.id ?? '');
  const [matSizeMm, setMatSizeMm] = useState('1000');
  const [markerSizeMm, setMarkerSizeMm] = useState('100');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!code.trim() || !branchId) {
      setErr(t('reasonRequired'));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await createStation(token, {
        code,
        branchId,
        matSizeMm: Number(matSizeMm),
        markerSizeMm: Number(markerSizeMm),
      });
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
        <SelectField
          label={t('filterBranch')}
          value={branchId}
          onChange={setBranchId}
          options={branches.map((b) => ({ value: b.id, label: `${b.code} — ${b.name}` }))}
        />
        <TextField label={t('matSize')} type="number" value={matSizeMm} onChange={setMatSizeMm} />
        <TextField
          label={t('markerSize')}
          type="number"
          value={markerSizeMm}
          onChange={setMarkerSizeMm}
        />
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
