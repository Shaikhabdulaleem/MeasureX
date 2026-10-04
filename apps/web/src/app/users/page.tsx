'use client';

import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Badge, Button, Modal, SelectField, Table, TextField } from '@/components/ui';
import {
  AdminUser,
  Branch,
  createUser,
  listBranches,
  listUsers,
  resetUserPassword,
  unlockUser,
  updateUser,
} from '@/lib/api';
import { StoredSession } from '@/lib/session';

export default function UsersPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('users')} requiredRoles={['admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [tempPassword, setTempPassword] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [u, b] = await Promise.all([listUsers(token), listBranches(token)]);
      setUsers(u.items);
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

  async function reset(id: string) {
    const res = await resetUserPassword(token, id);
    setTempPassword(res.tempPassword);
    load();
  }

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
        <Table
          head={[t('employeeId'), t('name'), t('role'), t('homeBranch'), t('status'), t('actions')]}
        >
          {users.map((u) => (
            <tr key={u.id} className="border-t border-slate-100">
              <td className="px-4 py-3 font-medium">{u.employeeId}</td>
              <td className="px-4 py-3">{u.name}</td>
              <td className="px-4 py-3">
                {t(
                  `role${u.role === 'team_leader' ? 'TeamLeader' : u.role === 'admin' ? 'Admin' : 'Labour'}`,
                )}
              </td>
              <td className="px-4 py-3">{branchName(u.homeBranchId)}</td>
              <td className="px-4 py-3">
                <div className="flex gap-1">
                  <Badge tone={u.status === 'active' ? 'green' : 'slate'}>{u.status}</Badge>
                  {u.lockedUntil && new Date(u.lockedUntil) > new Date() && (
                    <Badge tone="red">{t('locked')}</Badge>
                  )}
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1">
                  <Button onClick={() => reset(u.id)}>{t('resetPassword')}</Button>
                  <Button
                    onClick={async () => {
                      await unlockUser(token, u.id);
                      load();
                    }}
                  >
                    {t('unlock')}
                  </Button>
                  <Button
                    onClick={async () => {
                      await updateUser(token, u.id, {
                        status: u.status === 'active' ? 'inactive' : 'active',
                      });
                      load();
                    }}
                  >
                    {u.status === 'active' ? t('inactive') : t('active')}
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {showCreate && (
        <CreateUserModal
          token={token}
          branches={branches}
          onClose={() => setShowCreate(false)}
          onDone={(temp) => {
            setShowCreate(false);
            setTempPassword(temp);
            load();
          }}
        />
      )}

      {tempPassword && (
        <Modal title={t('resetPassword')} onClose={() => setTempPassword(null)}>
          <p className="text-sm text-slate-600">{t('tempPasswordIs')}</p>
          <p className="mt-2 select-all rounded-md bg-slate-100 px-3 py-2 font-mono text-lg">
            {tempPassword}
          </p>
          <div className="mt-6 flex justify-end">
            <Button variant="primary" onClick={() => setTempPassword(null)}>
              {t('close')}
            </Button>
          </div>
        </Modal>
      )}
    </>
  );
}

function CreateUserModal({
  token,
  branches,
  onClose,
  onDone,
}: {
  token: string;
  branches: Branch[];
  onClose: () => void;
  onDone: (tempPassword: string) => void;
}) {
  const { t } = useI18n();
  const [employeeId, setEmployeeId] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState('labour');
  const [homeBranchId, setHomeBranchId] = useState(branches[0]?.id ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!employeeId.trim() || !name.trim() || !homeBranchId) {
      setErr(t('reasonRequired'));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const res = await createUser(token, {
        employeeId,
        name,
        role,
        homeBranchId,
        adminScope: role === 'admin' ? ['all'] : undefined,
      });
      onDone(res.tempPassword);
    } catch {
      setErr(t('actionFailed'));
      setBusy(false);
    }
  }

  return (
    <Modal title={t('create')} onClose={onClose}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField label={t('employeeId')} value={employeeId} onChange={setEmployeeId} />
        <TextField label={t('name')} value={name} onChange={setName} />
        <SelectField
          label={t('role')}
          value={role}
          onChange={setRole}
          options={[
            { value: 'labour', label: t('roleLabour') },
            { value: 'team_leader', label: t('roleTeamLeader') },
            { value: 'admin', label: t('roleAdmin') },
          ]}
        />
        <SelectField
          label={t('homeBranch')}
          value={homeBranchId}
          onChange={setHomeBranchId}
          options={branches.map((b) => ({ value: b.id, label: `${b.code} — ${b.name}` }))}
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
