'use client';

import { useI18n } from '@/i18n/client';

export function LanguageToggle() {
  const { t, toggleLocale } = useI18n();
  return (
    <button
      type="button"
      onClick={toggleLocale}
      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
    >
      {t('language')}
    </button>
  );
}
