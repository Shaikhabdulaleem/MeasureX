import { BadRequestException, Injectable } from '@nestjs/common';
import ExcelJS from 'exceljs';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { shipmentScopeWhere } from '../common/scope';

export type ReportType = 'daily-volume' | 'productivity' | 'flags' | 'manual-entry-rate';
export type ReportFormat = 'xlsx' | 'csv';

export const REPORT_TYPES: ReportType[] = [
  'daily-volume',
  'productivity',
  'flags',
  'manual-entry-rate',
];

export interface ReportFilters {
  dateFrom?: string;
  dateTo?: string;
  branchId?: string;
}

export interface ReportFile {
  filename: string;
  mime: string;
  buffer: Buffer;
}

/** A tabular report: a title, column headers and rows of primitive cells. */
interface Table {
  title: string;
  headers: string[];
  rows: (string | number)[][];
}

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

@Injectable()
export class ReportsService {
  constructor(private readonly prisma: PrismaService) {}

  /**
   * Build a report as an xlsx or csv buffer (PRD §11). Pure and synchronous
   * (no Redis), so it is directly testable and the endpoint can stream it; the
   * BullMQ offload path (large exports → S3) wraps this same builder.
   */
  async generate(
    type: ReportType,
    format: ReportFormat,
    user: AuthUser,
    filters: ReportFilters,
  ): Promise<ReportFile> {
    if (!REPORT_TYPES.includes(type)) {
      throw new BadRequestException({ code: 'UNKNOWN_REPORT', message: `Unknown report: ${type}` });
    }
    const table = await this.buildTable(type, user, filters);
    const buffer = format === 'csv' ? toCsv(table) : await toXlsx(table);
    const ext = format === 'csv' ? 'csv' : 'xlsx';
    const mime = format === 'csv' ? 'text/csv' : XLSX_MIME;
    const stamp = new Date().toISOString().slice(0, 10);
    return { filename: `${type}_${stamp}.${ext}`, mime, buffer };
  }

  // --- report builders -------------------------------------------------------

  private async buildTable(
    type: ReportType,
    user: AuthUser,
    filters: ReportFilters,
  ): Promise<Table> {
    const scope = shipmentScopeWhere(user);
    const range = this.window(filters);
    const shipmentScope: Prisma.ShipmentWhereInput = {
      AND: [
        scope,
        { deletedAt: null },
        ...(filters.branchId ? [{ branchId: filters.branchId }] : []),
      ],
    };

    switch (type) {
      case 'daily-volume':
        return this.dailyVolume(shipmentScope, range);
      case 'productivity':
        return this.productivity(shipmentScope, range, false);
      case 'manual-entry-rate':
        return this.productivity(shipmentScope, range, true);
      case 'flags':
        return this.flags(scope, range);
    }
  }

  private async dailyVolume(
    shipmentScope: Prisma.ShipmentWhereInput,
    range: { from: Date; to: Date },
  ): Promise<Table> {
    const packages = await this.prisma.package.findMany({
      where: {
        deletedAt: null,
        status: 'active',
        shipment: { is: shipmentScope },
        confirmedAt: { gte: range.from, lte: range.to },
      },
      select: {
        shipmentId: true,
        confirmedAt: true,
        currentVersion: { select: { cbm: true, chargeableG: true } },
      },
    });

    // Group by UTC day.
    const byDay = new Map<
      string,
      { shipments: Set<string>; packages: number; cbm: Prisma.Decimal; chargeableG: number }
    >();
    for (const p of packages) {
      const day = p.confirmedAt ? p.confirmedAt.toISOString().slice(0, 10) : 'unknown';
      const row = byDay.get(day) ?? {
        shipments: new Set<string>(),
        packages: 0,
        cbm: new Prisma.Decimal(0),
        chargeableG: 0,
      };
      row.shipments.add(p.shipmentId);
      row.packages += 1;
      if (p.currentVersion) {
        row.cbm = row.cbm.add(p.currentVersion.cbm);
        row.chargeableG += p.currentVersion.chargeableG;
      }
      byDay.set(day, row);
    }

    const rows = [...byDay.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, v]) => [
        day,
        v.shipments.size,
        v.packages,
        Number(v.cbm.toFixed(4)),
        Number((v.chargeableG / 1000).toFixed(3)),
      ]);

    return {
      title: 'Daily volume',
      headers: ['Date (UTC)', 'Shipments', 'Packages', 'CBM', 'Chargeable (kg)'],
      rows,
    };
  }

  private async productivity(
    shipmentScope: Prisma.ShipmentWhereInput,
    range: { from: Date; to: Date },
    manualRateOnly: boolean,
  ): Promise<Table> {
    const packages = await this.prisma.package.findMany({
      where: {
        deletedAt: null,
        status: 'active',
        shipment: { is: shipmentScope },
        confirmedAt: { gte: range.from, lte: range.to },
      },
      select: {
        measuredBy: true,
        measuredByUser: { select: { employeeId: true, name: true } },
        currentVersion: { select: { method: true } },
      },
    });

    const byUser = new Map<
      string,
      { employeeId: string; name: string; total: number; manual: number }
    >();
    for (const p of packages) {
      const key = p.measuredBy ?? 'unknown';
      const row = byUser.get(key) ?? {
        employeeId: p.measuredByUser?.employeeId ?? 'unknown',
        name: p.measuredByUser?.name ?? 'unknown',
        total: 0,
        manual: 0,
      };
      row.total += 1;
      if (p.currentVersion?.method === 'manual') row.manual += 1;
      byUser.set(key, row);
    }

    const sorted = [...byUser.values()].sort((a, b) => b.total - a.total);

    if (manualRateOnly) {
      return {
        title: 'Manual-entry rate',
        headers: ['Employee ID', 'Name', 'Packages', 'Manual entries', 'Manual rate (%)'],
        rows: sorted.map((u) => [
          u.employeeId,
          u.name,
          u.total,
          u.manual,
          u.total ? Number(((u.manual / u.total) * 100).toFixed(1)) : 0,
        ]),
      };
    }

    return {
      title: 'Productivity per worker',
      headers: ['Employee ID', 'Name', 'Packages measured', 'Manual entries'],
      rows: sorted.map((u) => [u.employeeId, u.name, u.total, u.manual]),
    };
  }

  private async flags(
    scope: Prisma.ShipmentWhereInput,
    range: { from: Date; to: Date },
  ): Promise<Table> {
    const flags = await this.prisma.flag.findMany({
      where: {
        deletedAt: null,
        createdAt: { gte: range.from, lte: range.to },
        shipment: { is: scope },
      },
      orderBy: { createdAt: 'desc' },
      include: { shipment: { select: { awb: true } } },
    });

    return {
      title: 'Flags',
      headers: ['Created (UTC)', 'AWB', 'Type', 'Status', 'Note'],
      rows: flags.map((f) => [
        f.createdAt.toISOString(),
        f.shipment?.awb ?? '',
        f.type,
        f.status,
        f.note ?? '',
      ]),
    };
  }

  private window(filters: ReportFilters): { from: Date; to: Date } {
    const now = new Date();
    return {
      from: filters.dateFrom ? new Date(filters.dateFrom) : new Date(now.getTime() - 86_400_000),
      to: filters.dateTo ? new Date(filters.dateTo) : now,
    };
  }
}

// --- serializers -------------------------------------------------------------

async function toXlsx(table: Table): Promise<Buffer> {
  const wb = new ExcelJS.Workbook();
  wb.creator = 'MeasureX';
  wb.created = new Date();
  const ws = wb.addWorksheet(table.title.slice(0, 31));
  const header = ws.addRow(table.headers);
  header.font = { bold: true };
  for (const row of table.rows) ws.addRow(row);
  ws.columns.forEach((col) => {
    col.width = 18;
  });
  const out = await wb.xlsx.writeBuffer();
  return Buffer.from(out);
}

function toCsv(table: Table): Buffer {
  const escape = (cell: string | number): string => {
    const s = String(cell);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [table.headers, ...table.rows].map((r) => r.map(escape).join(','));
  // BOM so Excel opens UTF-8 CSV with the correct encoding.
  return Buffer.from('﻿' + lines.join('\r\n'), 'utf8');
}
