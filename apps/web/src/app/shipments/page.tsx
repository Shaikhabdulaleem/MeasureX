'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useI18n } from '@/i18n/client';
import { AppShell } from '@/components/AppShell';
import { Table } from '@/components/ui';
import { listShipments, Shipment, ShipmentFilters } from '@/lib/api';
import { StoredSession } from '@/lib/session';

const kg2 = (g: number) => `${(g / 1000).toFixed(2)} kg`;
const kg1 = (g: number) => `${(g / 1000).toFixed(1)} kg`;

export default function ShipmentsPage() {
  const { t } = useI18n();
  return <AppShell title={t('shipments')}>{(session) => <Body session={session} />}</AppShell>;
}

function Body({ session }: { session: StoredSession }) {
  const { t } = useI18n();
  const token = session.accessToken;
  const [items, setItems] = useState<Shipment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [filters, setFilters] = useState<ShipmentFilters>({});

  const load = useCallback(
    async (applied: ShipmentFilters) => {
      setLoading(true);
      setError(false);
      try {
        const res = await listShipments(token, applied);
        setItems(res.items);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    },
    [token],
  );

  useEffect(() => {
    void load({});
  }, [load]);

  return (
    <>
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
        <Table
          head={[
            t('filterAwb'),
            t('status'),
            t('pieces'),
            t('cbm'),
            t('volumetric'),
            t('chargeable'),
            t('createdAt'),
          ]}
        >
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
              <td className="px-4 py-3 text-slate-500">{new Date(s.createdAt).toLocaleString()}</td>
            </tr>
          ))}
        </Table>
      )}
    </>
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
