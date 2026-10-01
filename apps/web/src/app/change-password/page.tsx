'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useI18n } from '@/i18n/client';
import { LanguageToggle } from '@/components/LanguageToggle';
import { changePassword } from '@/lib/api';
import { clearSession, getSession } from '@/lib/session';

export default function ChangePasswordPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getSession()) router.replace('/login');
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next.length < 8) {
      setError(t('passwordTooShort'));
      return;
    }
    if (next !== confirm) {
      setError(t('passwordsDoNotMatch'));
      return;
    }
    const session = getSession();
    if (!session) {
      router.replace('/login');
      return;
    }
    setBusy(true);
    try {
      await changePassword(session.accessToken, current, next);
      // Password change revokes sessions server-side; require a fresh login.
      clearSession();
      router.replace('/login');
    } catch {
      setError(t('changePasswordError'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-200">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">{t('changePasswordTitle')}</h1>
            <p className="text-sm text-slate-500">{t('changePasswordHint')}</p>
          </div>
          <LanguageToggle />
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <Field id="current" label={t('currentPassword')} value={current} onChange={setCurrent} />
          <Field id="next" label={t('newPassword')} value={next} onChange={setNext} />
          <Field id="confirm" label={t('confirmPassword')} value={confirm} onChange={setConfirm} />

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand px-4 py-2.5 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
          >
            {busy ? t('saving') : t('save')}
          </button>
        </form>
      </div>
    </main>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="new-password"
        required
        className="w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand focus:ring-1 focus:ring-brand"
      />
    </div>
  );
}
