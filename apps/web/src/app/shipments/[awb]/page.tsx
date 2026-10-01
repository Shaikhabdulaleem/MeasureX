'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useI18n } from '@/i18n/client';
import { LanguageToggle } from '@/components/LanguageToggle';
import { getPhotoUrl, getShipment, ShipmentDetail } from '@/lib/api';
import { getSession } from '@/lib/session';

const kg2 = (g: number) => `${(g / 1000).toFixed(2)} kg`;
const kg1 = (g: number) => `${(g / 1000).toFixed(1)} kg`;

export default function ShipmentDetailPage() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useParams<{ awb: string }>();
  const awb = decodeURIComponent(params.awb);
  const [shipment, setShipment] = useState<ShipmentDetail | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const s = getSession();
    if (!s) {
      router.replace('/login');
      return;
    }
    getShipment(s.accessToken, awb)
      .then(setShipment)
      .catch(() => setError(true));
  }, [awb, router]);

  return (
    <main className="min-h-screen">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="text-lg font-bold text-brand">
            {t('appName')}
          </Link>
          <span className="text-slate-400">/</span>
          <Link href="/shipments" className="text-slate-600 hover:underline">
            {t('shipments')}
          </Link>
          <span className="text-slate-400">/</span>
          <h1 className="text-lg font-semibold text-slate-800">{awb}</h1>
        </div>
        <LanguageToggle />
      </header>

      <section className="mx-auto max-w-5xl p-6">
        <Link href="/shipments" className="text-sm text-brand hover:underline">
          {t('backToShipments')}
        </Link>

        {error && <p className="mt-4 text-red-600">{t('errorLoading')}</p>}
        {!error && !shipment && <p className="mt-4 text-slate-500">{t('loading')}</p>}

        {shipment && (
          <>
            <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:grid-cols-5">
              <Stat label={t('status')} value={shipment.status} />
              <Stat label={t('pieces')} value={String(shipment.totals.pieces)} />
              <Stat label={t('cbm')} value={shipment.totals.cbm.toFixed(4)} />
              <Stat label={t('volumetric')} value={kg2(shipment.totals.volumetricG)} />
              <Stat label={t('chargeable')} value={kg1(shipment.totals.chargeableG)} emphasise />
            </div>

            <div className="mt-6 overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-slate-500">
                  <tr>
                    <th className="px-4 py-3">{t('packageNo')}</th>
                    <th className="px-4 py-3">{t('status')}</th>
                    <th className="px-4 py-3">{t('dimensions')}</th>
                    <th className="px-4 py-3">{t('cbm')}</th>
                    <th className="px-4 py-3">{t('chargeable')}</th>
                    <th className="px-4 py-3">{t('method')}</th>
                    <th className="px-4 py-3">{t('photo')}</th>
                  </tr>
                </thead>
                <tbody>
                  {shipment.packages.map((p) => {
                    const v = p.currentVersion;
                    return (
                      <tr key={p.id} className="border-t border-slate-100">
                        <td className="px-4 py-3 font-medium">
                          {p.packageNumber != null
                            ? `PKG ${String(p.packageNumber).padStart(2, '0')}`
                            : '—'}
                        </td>
                        <td className="px-4 py-3">{p.status}</td>
                        <td className="px-4 py-3">
                          {v ? `${v.billingLCm} × ${v.billingWCm} × ${v.billingHCm} cm` : '—'}
                        </td>
                        <td className="px-4 py-3">{v ? v.cbm.toFixed(4) : '—'}</td>
                        <td className="px-4 py-3 font-semibold">{v ? kg1(v.chargeableG) : '—'}</td>
                        <td className="px-4 py-3">{v?.method ?? '—'}</td>
                        <td className="px-4 py-3">
                          {p.photos.length > 0 ? (
                            <PhotoButton photoId={p.photos[0].id} label={t('viewPhoto')} />
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

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

function PhotoButton({ photoId, label }: { photoId: string; label: string }) {
  const [busy, setBusy] = useState(false);
  async function open() {
    const s = getSession();
    if (!s) return;
    setBusy(true);
    try {
      const url = await getPhotoUrl(s.accessToken, photoId);
      window.open(url, '_blank', 'noopener');
    } catch {
      // ignored — a 403 means this role cannot view photos.
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
