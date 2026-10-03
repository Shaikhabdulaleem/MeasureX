import { Controller, Get, Param, Query, Req, Res } from '@nestjs/common';
import { Request, Response } from 'express';
import { Role } from '@prisma/client';
import { ReportFormat, ReportType, ReportsService } from './reports.service';
import { AuditService } from '../audit/audit.service';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

/**
 * GET /reports/{type} — build and stream a report (Team Leader / Admin, PRD §11).
 * Returns the file inline for immediate download. The buffer is produced
 * synchronously by ReportsService (no Redis); a BullMQ offload to S3 is the
 * designated extension point for very large exports.
 */
@Controller('reports')
export class ReportsController {
  constructor(
    private readonly reports: ReportsService,
    private readonly audit: AuditService,
  ) {}

  @Get(':type')
  @Roles(Role.team_leader, Role.admin)
  async get(
    @Param('type') type: ReportType,
    @CurrentUser() user: AuthUser,
    @Res() res: Response,
    @Req() req: Request,
    @Query('format') format: ReportFormat = 'xlsx',
    @Query('dateFrom') dateFrom?: string,
    @Query('dateTo') dateTo?: string,
    @Query('branchId') branchId?: string,
  ): Promise<void> {
    const fmt: ReportFormat = format === 'csv' ? 'csv' : 'xlsx';
    const file = await this.reports.generate(type, fmt, user, { dateFrom, dateTo, branchId });

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'report',
      entityId: type,
      action: 'report_exported',
      after: {
        format: fmt,
        dateFrom: dateFrom ?? null,
        dateTo: dateTo ?? null,
        branchId: branchId ?? null,
      },
      ip: req.ip,
    });

    res.setHeader('Content-Type', file.mime);
    res.setHeader('Content-Disposition', `attachment; filename="${file.filename}"`);
    res.setHeader('Content-Length', file.buffer.length);
    res.end(file.buffer);
  }
}
