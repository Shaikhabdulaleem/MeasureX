'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Badge, Button, Modal, Table, TextField } from '@/components/ui';
import {
  correctPackage,
  createRemeasure,
  getPackageVersions,
  getPhotoUrl,
  getShipment,
  reopenShipment,
  ShipmentDetail,
  PackageRow,
  VersionRow,
  voidPackage,
} from '@/lib/api';
import { StoredSession } from '@/lib/session';

const kg2 = (g: number) => `${(g / 1000).toFixed(2)} kg`;
const kg1 = (g: number) => `${(g / 1000).toFixed(1)} kg`;
const pkgLabel = (n: number | null) => (n != null ? `PKG ${String(n).padStart(2, '0')}` : '—');

export default function ShipmentDetailPage() {
  const params = useParams<{ awb: string }>();
  const awb = decodeURIComponent(params.awb);
  return <AppShell title={awb}>{(session) => <Detail awb={awb} session={session} />}</AppShell>;
}

function Detail({ awb, session }: { awb: string; session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const isTL = session.user.role === 'team_leader' || session.user.role === 'admin';
  const [shipment, setShipment] = useState<ShipmentDetail | null>(null);
  const [error, setError] = useState(false);
  const [modal, setModal] = useState<ModalState>(null);

  const load = useCallback(() => {
    getShipment(token, awb)
      .then(setShipment)
      .catch(() => setError(true));
  }, [token, awb]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <p className="text-red-600">{t('errorLoading')}</p>;
  if (!shipment) return <p className="text-slate-500">{t('loading')}</p>;

  const activePackages = shipment.packages.filter((p) => p.status === 'active');

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Badge tone={shipment.status === 'completed' ? 'green' : 'blue'}>{shipment.status}</Badge>
        {shipment.flags.map((f) => (
          <Badge key={f} tone="amber">
            {f}
          </Badge>
        ))}
        <div className="ms-auto flex gap-2">
          {isTL && shipment.status === 'completed' && (
            <>
              <Button onClick={() => setModal({ kind: 'reopen' })}>{t('reopen')}</Button>
              <Button variant="primary" onClick={() => setModal({ kind: 'remeasure' })}>
                {t('requestRemeasure')}
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:grid-cols-5">
        <Stat label={t('pieces')} value={String(shipment.totals.pieces)} />
        <Stat label={t('cbm')} value={shipment.totals.cbm.toFixed(4)} />
        <Stat label={t('volumetric')} value={kg2(shipment.totals.volumetricG)} />
        <Stat label={t('actualWeight')} value={kg2(shipment.totals.actualG)} />
        <Stat label={t('chargeable')} value={kg1(shipment.totals.chargeableG)} emphasise />
      </div>

      <Table
        head={[
          t('packageNo'),
          t('status'),
          t('dimensions'),
          t('cbm'),
          t('chargeable'),
          t('method'),
          t('photo'),
          t('actions'),
        ]}
      >
        {shipment.packages.map((p) => {
          const v = p.currentVersion;
          return (
            <tr key={p.id} className="border-t border-slate-100 align-top">
              <td className="px-4 py-3 font-medium">{pkgLabel(p.packageNumber)}</td>
              <td className="px-4 py-3">
                <Badge
                  tone={p.status === 'active' ? 'green' : p.status === 'void' ? 'red' : 'slate'}
                >
                  {p.status}
                </Badge>
              </td>
              <td className="px-4 py-3">
                {v ? `${v.billingLCm} × ${v.billingWCm} × ${v.billingHCm} cm` : '—'}
              </td>
              <td className="px-4 py-3">{v ? v.cbm.toFixed(4) : '—'}</td>
              <td className="px-4 py-3 font-semibold">{v ? kg1(v.chargeableG) : '—'}</td>
              <td className="px-4 py-3">{v?.method ?? '—'}</td>
              <td className="px-4 py-3">
                {p.photos.length > 0 ? (
                  <PhotoButton token={token} photoId={p.photos[0].id} label={t('viewPhoto')} />
                ) : (
                  '—'
                )}
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1">
                  <Button onClick={() => setModal({ kind: 'versions', pkg: p })}>
                    {t('viewVersions')}
                  </Button>
                  {isTL && p.status === 'active' && (
                    <>
                      <Button onClick={() => setModal({ kind: 'correct', pkg: p })}>
                        {t('correct')}
                      </Button>
                      <Button variant="danger" onClick={() => setModal({ kind: 'void', pkg: p })}>
                        {t('void')}
                      </Button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </Table>

      {modal?.kind === 'correct' && (
        <CorrectModal
          token={token}
          pkg={modal.pkg}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            load();
          }}
        />
      )}
      {modal?.kind === 'void' && (
        <ReasonModal
          title={`${t('void')} — ${pkgLabel(modal.pkg.packageNumber)}`}
          onClose={() => setModal(null)}
          onSubmit={async (reason) => {
            await voidPackage(token, modal.pkg.id, reason);
            setModal(null);
            load();
          }}
        />
      )}
      {modal?.kind === 'reopen' && (
        <ReasonModal
          title={t('reopen')}
          onClose={() => setModal(null)}
          onSubmit={async (reason) => {
            await reopenShipment(token, awb, reason);
            setModal(null);
            load();
          }}
        />
      )}
      {modal?.kind === 'remeasure' && (
        <RemeasureModal
          token={token}
          shipmentId={shipment.id}
          packages={activePackages}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            load();
          }}
        />
      )}
      {modal?.kind === 'versions' && (
        <VersionsModal token={token} pkg={modal.pkg} onClose={() => setModal(null)} />
      )}
    </>
  );
}

type ModalState =
  | null
  | { kind: 'correct'; pkg: PackageRow }
  | { kind: 'void'; pkg: PackageRow }
  | { kind: 'reopen' }
  | { kind: 'remeasure' }
  | { kind: 'versions'; pkg: PackageRow };

function Stat({ label, value, emphasise }: { label: string; value: string; emphasise?: boolean }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 ${emphasise ? 'text-lg font-bold text-slate-900' : 'text-slate-700'}`}>
        {value}
      </p>
    </div>
  );
}

function CorrectModal({
  token,
  pkg,
  onClose,
  onDone,
}: {
  token: string;
  pkg: PackageRow;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const v = pkg.currentVersion;
  const [length, setLength] = useState(String(v?.lengthMm ?? ''));
  const [width, setWidth] = useState(String(v?.widthMm ?? ''));
  const [height, setHeight] = useState(String(v?.heightMm ?? ''));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!reason.trim()) {
      setErr(t('reasonRequired'));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await correctPackage(token, pkg.id, {
        lengthMm: Number(length),
        widthMm: Number(width),
        heightMm: Number(height),
        reason,
      });
      onDone();
    } catch {
      setErr(t('actionFailed'));
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`${t('correctionTitle')} — PKG ${String(pkg.packageNumber ?? 0).padStart(2, '0')}`}
      onClose={onClose}
    >
      <div className="grid grid-cols-2 gap-6">
        <div>
          <p className="mb-2 text-sm font-semibold text-slate-500">{t('original')}</p>
          <ul className="space-y-1 text-sm text-slate-700">
            <li>
              {t('length')}: <b>{v?.lengthMm ?? '—'}</b>
            </li>
            <li>
              {t('width')}: <b>{v?.widthMm ?? '—'}</b>
            </li>
            <li>
              {t('height')}: <b>{v?.heightMm ?? '—'}</b>
            </li>
            <li>
              {t('chargeable')}: <b>{v ? kg1(v.chargeableG) : '—'}</b>
            </li>
          </ul>
        </div>
        <div className="space-y-2">
          <p className="text-sm font-semibold text-slate-500">{t('newValues')}</p>
          <TextField label={t('length')} type="number" value={length} onChange={setLength} />
          <TextField label={t('width')} type="number" value={width} onChange={setWidth} />
          <TextField label={t('height')} type="number" value={height} onChange={setHeight} />
        </div>
      </div>
      <div className="mt-4">
        <TextField label={t('reason')} value={reason} onChange={setReason} />
      </div>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onClose}>{t('cancel')}</Button>
        <Button variant="primary" onClick={submit} disabled={busy}>
          {busy ? t('saving') : t('submit')}
        </Button>
      </div>
    </Modal>
  );
}

function ReasonModal({
  title,
  onClose,
  onSubmit,
}: {
  title: string;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!reason.trim()) {
      setErr(t('reasonRequired'));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSubmit(reason);
    } catch {
      setErr(t('actionFailed'));
      setBusy(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <TextField label={t('reason')} value={reason} onChange={setReason} />
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onClose}>{t('cancel')}</Button>
        <Button variant="primary" onClick={submit} disabled={busy}>
          {busy ? t('saving') : t('submit')}
        </Button>
      </div>
    </Modal>
  );
}

const REMEASURE_REASONS = [
  'low_confidence',
  'incorrect_dimensions',
  'bad_photo',
  'device_issue',
  'customer_dispute',
  'manual_verification',
  'other',
];

function RemeasureModal({
  token,
  shipmentId,
  packages,
  onClose,
  onDone,
}: {
  token: string;
  shipmentId: string;
  packages: PackageRow[];
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<string[]>(packages.map((p) => p.id));
  const [reason, setReason] = useState('low_confidence');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function submit() {
    if (selected.length === 0) return;
    if (reason === 'other' && !note.trim()) {
      setErr(t('reasonRequired'));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await createRemeasure(token, {
        shipmentId,
        packageIds: selected,
        reason,
        note: note || undefined,
      });
      onDone();
    } catch {
      setErr(t('actionFailed'));
      setBusy(false);
    }
  }

  return (
    <Modal title={t('requestRemeasure')} onClose={onClose}>
      <div className="space-y-2">
        {packages.map((p) => (
          <label key={p.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(p.id)}
              onChange={() => toggle(p.id)}
            />
            {pkgLabel(p.packageNumber)}
          </label>
        ))}
      </div>
      <div className="mt-4">
        <label className="flex flex-col text-sm">
          <span className="mb-1 text-slate-500">{t('reason')}</span>
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-2"
          >
            {REMEASURE_REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-3">
        <TextField label={t('note')} value={note} onChange={setNote} />
      </div>
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onClose}>{t('cancel')}</Button>
        <Button variant="primary" onClick={submit} disabled={busy || selected.length === 0}>
          {busy ? t('saving') : t('submit')}
        </Button>
      </div>
    </Modal>
  );
}

function VersionsModal({
  token,
  pkg,
  onClose,
}: {
  token: string;
  pkg: PackageRow;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [versions, setVersions] = useState<VersionRow[] | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);

  useEffect(() => {
    getPackageVersions(token, pkg.id)
      .then((r) => {
        setVersions(r.items);
        setCurrentId(r.currentVersionId);
      })
      .catch(() => setVersions([]));
  }, [token, pkg.id]);

  return (
    <Modal title={`${t('versionHistory')} — ${pkgLabel(pkg.packageNumber)}`} onClose={onClose}>
      {!versions ? (
        <p className="text-slate-500">{t('loading')}</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {versions.map((v) => (
            <div
              key={v.id}
              className={`rounded-lg border p-3 text-sm ${
                v.id === currentId ? 'border-brand bg-teal-50' : 'border-slate-200'
              }`}
            >
              <p className="mb-1 font-semibold">
                {t('version')} {v.versionNo} {v.id === currentId ? '•' : ''}
              </p>
              <p>
                {v.billingLCm} × {v.billingWCm} × {v.billingHCm} cm
              </p>
              <p>
                {t('cbm')}: {v.cbm.toFixed(4)} · {t('chargeable')}: {kg1(v.chargeableG)}
              </p>
              <p className="text-slate-500">
                {v.method}
                {v.reason ? ` · ${v.reason}` : ''}
              </p>
              <p className="text-xs text-slate-400">{new Date(v.createdAt).toLocaleString()}</p>
            </div>
          ))}
        </div>
      )}
      <div className="mt-6 flex justify-end">
        <Button onClick={onClose}>{t('close')}</Button>
      </div>
    </Modal>
  );
}

function PhotoButton({ token, photoId, label }: { token: string; photoId: string; label: string }) {
  const [busy, setBusy] = useState(false);
  async function open() {
    setBusy(true);
    try {
      const url = await getPhotoUrl(token, photoId);
      window.open(url, '_blank', 'noopener');
    } catch {
      // 403 → this role cannot view photos
    } finally {
      setBusy(false);
    }
  }
  return (
    <button
      type="button"
      onClick={open}
      disabled={busy}
      className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-brand hover:bg-slate-50 disabled:opacity-50"
    >
      {label}
    </button>
  );
}
