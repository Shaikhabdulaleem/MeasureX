'use client';

import { createContext, useContext, useMemo, useState, ReactNode } from 'react';
import { DEFAULT_LOCALE, LOCALE_COOKIE, Locale, dir, getDictionary } from './dictionaries';

interface I18nValue {
  locale: Locale;
  t: (key: string) => string;
  toggleLocale: () => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: ReactNode;
}) {
  const [locale, setLocale] = useState<Locale>(initialLocale);

  const value = useMemo<I18nValue>(() => {
    const dict = getDictionary(locale);
    return {
      locale,
      t: (key: string) => dict[key] ?? key,
      toggleLocale: () => {
        const next: Locale = locale === 'en' ? 'ar' : 'en';
        document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000`;
        document.documentElement.lang = next;
        document.documentElement.dir = dir(next);
        setLocale(next);
      },
    };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // Safe fallback so components never crash outside a provider.
    const dict = getDictionary(DEFAULT_LOCALE);
    return {
      locale: DEFAULT_LOCALE,
      t: (key: string) => dict[key] ?? key,
      toggleLocale: () => undefined,
    };
  }
  return ctx;
}
