import type { Metadata } from 'next';
import { cookies } from 'next/headers';
import './globals.css';
import { I18nProvider } from '@/i18n/client';
import { DEFAULT_LOCALE, LOCALE_COOKIE, Locale, LOCALES, dir } from '@/i18n/dictionaries';

export const metadata: Metadata = {
  title: 'MeasureX',
  description: 'Aymakan shipment dimensioning and weighing',
};

function resolveLocale(): Locale {
  const value = cookies().get(LOCALE_COOKIE)?.value as Locale | undefined;
  return value && LOCALES.includes(value) ? value : DEFAULT_LOCALE;
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = resolveLocale();
  return (
    <html lang={locale} dir={dir(locale)}>
      <body>
        <I18nProvider initialLocale={locale}>{children}</I18nProvider>
      </body>
    </html>
  );
}
