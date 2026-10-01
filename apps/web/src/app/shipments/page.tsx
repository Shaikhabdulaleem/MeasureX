'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useI18n } from '@/i18n/client';
import { LanguageToggle } from '@/components/LanguageToggle';
import { listShipments, logout, Shipment, ShipmentFilters } from '@/lib/api';
import { clearSession, getSession } from '@/lib/session';

const kg2 = (g: number) => `${(g / 1000).toFixed(2)} kg`;
const kg1 = (g: number) => `${(g / 1000).toFixed(1)} kg`;

export default function ShipmentsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [items, setItems] = useState<Shipment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [filters, setFilters] = useState<ShipmentFilters>({});

  const load = useCallback(
    async (applied: ShipmentFilters) => {
      const s = getSession();
      if (!s) {
        router.replace('/login');
        return;
      }
      setLoading(true);
      setError(false);
      try {
        const res = await listShipments(s.accessToken, applied);
        setItems(res.items);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    const s = getSession();
    if (!s) {
      router.replace('/login');
      return;
    }
    if (s.user.mustChangePassword) {
      router.replace('/change-password');
      return;
    }
    setReady(true);
    void load({});
  }, [router, load]);

  async function onSignOut() {
    const s = getSession();
    if (s) await logout(s.accessToken, s.refreshToken);
    clearSession();
    router.replace('/login');
  }

  if (!ready) return null;

  return (
    <main className="min-h-screen">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="text-lg font-bold text-brand">
            {t('appName')}
          </Link>
          <span className="text-slate-400">/</span>
          <h1 className="text-lg font-semibold text-slate-800">{t('shipments')}</h1>
        </div>
        <div className="flex items-center gap-3">
          <LanguageToggle />
          <button
            type="button"
            onClick={onSignOut}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            {t('signOut')}
          </button>
        </div>
      </header>

      <section className="mx-auto max-w-6xl p-6">
        <form
          className="mb-4 grid grid-cols-1 gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:grid-cols-2 lg:grid-cols-6"
          onSubmit={(e) => {
            e.preventDefault();
            void load(filters);
          }}
        >
          <Field
            label={t('filterAwb')}
            value={filters.awb ?? ''}
            onChange={(v) => setFilters((f) => ({ ...f, awb: v }))}
          />
          <Field
            label={t('filterBranch')}
            value={filters.branchId ?? ''}
            onChange={(v) => setFilters((f) => ({ ...f, branchId: v }))}
          />
          <Field
            label={t('filterEmployee')}
            value={filters.employeeId ?? ''}
            onChange={(v) => setFilters((f) => ({ ...f, employeeId: v }))}
          />
          <Field
            label={t('filterDateFrom')}
            type="date"
            value={filters.dateFrom?.slice(0, 10) ?? ''}
            onChange={(v) =>
              setFilters((f) => ({ ...f, dateFrom: v ? new Date(v).toISOString() : undefined }))
            }
          />
          <Field
            label={t('filterDateTo')}
            type="date"
            value={filters.dateTo?.slice(0, 10) ?? ''}
            onChange={(v) =>
              setFilters((f) => ({ ...f, dateTo: v ? new Date(v).toISOString() : undefined }))
            }
          />
          <div className="flex items-end gap-2">
            <button
              type="submit"
              className="rounded-md bg-brand px-4 py-2 text-sm font-semibold text-white"
            >
              {t('apply')}
            </button>
            <button
              type="button"
              onClick={() => {
                setFilters({});
                void load({});
              }}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
            >
              {t('clearFilters')}
            </button>
          </div>
        </form>

        {loading && <p className="text-slate-500">{t('loading')}</p>}
        {error && <p className="text-red-600">{t('errorLoading')}</p>}
        {!loading && !error && items.length === 0 && (
          <p className="text-slate-500">{t('noShipments')}</p>
        )}

        {!loading && !error && items.length > 0 && (
          <div className="overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-500">
                <tr>
                  <th className="px-4 py-3">{t('filterAwb')}</th>
                  <th className="px-4 py-3">{t('status')}</th>
                  <th className="px-4 py-3">{t('pieces')}</th>
                  <th className="px-4 py-3">{t('cbm')}</th>
                  <th className="px-4 py-3">{t('volumetric')}</th>
                  <th className="px-4 py-3">{t('chargeable')}</th>
                  <th className="px-4 py-3">{t('createdAt')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium">
                      <Link
                        href={`/shipments/${encodeURIComponent(s.awb)}`}
                        className="text-brand hover:underline"
                      >
                        {s.awb}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{s.status}</td>
                    <td className="px-4 py-3">{s.totals.pieces}</td>
                    <td className="px-4 py-3">{s.totals.cbm.toFixed(4)}</td>
                    <td className="px-4 py-3">{kg2(s.totals.volumetricG)}</td>
                    <td className="px-4 py-3 font-semibold">{kg1(s.totals.chargeableG)}</td>
                    <td className="px-4 py-3 text-slate-500">
                      {new Date(s.createdAt).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="flex flex-col text-sm">
      <span className="mb-1 text-slate-500">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 px-3 py-2 focus:border-brand focus:outline-none"
      />
    </label>
  );
}
