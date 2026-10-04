'use client';

import { useEffect, useState } from 'react';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Button, Card, TextField } from '@/components/ui';
import { EffectiveConfig, getConfig, updateConfig } from '@/lib/api';
import { StoredSession } from '@/lib/session';

export default function ConfigPage() {
  const { t } = useI18n();
  return (
    <AppShell title={t('configuration')} requiredRoles={['admin']}>
      {(session) => <Body session={session} />}
    </AppShell>
  );
}

const NUMERIC_FIELDS: { key: keyof EffectiveConfig; label: string }[] = [
  { key: 'volumetricDivisor', label: 'Volumetric divisor' },
  { key: 'chargeableStepKg', label: 'Chargeable step (kg)' },
  { key: 'minDimensionCm', label: 'Min dimension (cm)' },
  { key: 'maxDimensionCm', label: 'Max dimension (cm)' },
  { key: 'idleAutoCompleteMinutes', label: 'Idle auto-complete (min)' },
];

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [cfg, setCfg] = useState<EffectiveConfig | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    getConfig(token)
      .then((c) => {
        setCfg(c);
        setDraft({
          awbRegex: c.awbRegex,
          volumetricDivisor: String(c.volumetricDivisor),
          chargeableStepKg: String(c.chargeableStepKg),
          minDimensionCm: String(c.minDimensionCm),
          maxDimensionCm: String(c.maxDimensionCm),
          idleAutoCompleteMinutes: String(c.idleAutoCompleteMinutes),
        });
      })
      .catch(() => setError(true));
  }, [token]);

  async function save() {
    setBusy(true);
    setSaved(false);
    setMsg(null);
    try {
      const body: Record<string, unknown> = {
        awbRegex: draft.awbRegex,
        volumetricDivisor: Number(draft.volumetricDivisor),
        chargeableStepKg: Number(draft.chargeableStepKg),
        minDimensionCm: Number(draft.minDimensionCm),
        maxDimensionCm: Number(draft.maxDimensionCm),
        idleAutoCompleteMinutes: Number(draft.idleAutoCompleteMinutes),
        weightRequired: cfg?.weightRequired,
        mediumConfirmAllowed: cfg?.mediumConfirmAllowed,
      };
      const next = await updateConfig(token, body);
      setCfg(next);
      setSaved(true);
    } catch (e) {
      setMsg((e as { message?: string }).message ?? t('actionFailed'));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="text-red-600">{t('errorLoading')}</p>;
  if (!cfg) return <p className="text-slate-500">{t('loading')}</p>;

  return (
    <Card className="max-w-2xl">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextField
          label="AWB regex"
          value={draft.awbRegex ?? ''}
          onChange={(v) => setDraft((d) => ({ ...d, awbRegex: v }))}
        />
        {NUMERIC_FIELDS.map((f) => (
          <TextField
            key={f.key}
            label={f.label}
            type="number"
            value={draft[f.key] ?? ''}
            onChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))}
          />
        ))}
      </div>

      <div className="mt-4 space-y-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cfg.weightRequired}
            onChange={(e) => setCfg({ ...cfg, weightRequired: e.target.checked })}
          />
          Actual weight required
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cfg.mediumConfirmAllowed}
            onChange={(e) => setCfg({ ...cfg, mediumConfirmAllowed: e.target.checked })}
          />
          Medium confidence confirm allowed
        </label>
      </div>

      {msg && <p className="mt-3 text-sm text-red-600">{msg}</p>}
      {saved && <p className="mt-3 text-sm text-emerald-600">{t('saved')}</p>}

      <div className="mt-5">
        <Button variant="primary" onClick={save} disabled={busy}>
          {busy ? t('saving') : t('save')}
        </Button>
      </div>
    </Card>
  );
}
