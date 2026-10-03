import { Body, Controller, Get, HttpCode, HttpStatus, Post, Query, Req } from '@nestjs/common';
import { Request } from 'express';
import { SyncService } from './sync.service';
import { SyncBatchDto } from './dto/sync.dto';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller('sync')
export class SyncController {
  constructor(private readonly sync: SyncService) {}

  /**
   * POST /sync/batch — upload up to 50 offline packages (PRD §10, §13).
   * Idempotent per item; partial success returns per-item results.
   */
  @Post('batch')
  @HttpCode(HttpStatus.OK)
  async batch(@Body() dto: SyncBatchDto, @CurrentUser() user: AuthUser, @Req() req: Request) {
    const results = await this.sync.batch(dto, user, req.ip);
    return { results };
  }

  /** GET /sync/status — the server's view of this device's recent packages. */
  @Get('status')
  status(@Query('deviceId') deviceId: string | undefined, @CurrentUser() user: AuthUser) {
    return this.sync.status(deviceId, user);
  }
}
