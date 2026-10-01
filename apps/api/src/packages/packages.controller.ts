import {
  BadRequestException,
  Body,
  Controller,
  Headers,
  Param,
  Post,
  Req,
  Res,
} from '@nestjs/common';
import { Request, Response } from 'express';
import { PackagesService } from './packages.service';
import { PackageCreateDto } from './dto/package.dto';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller('shipments')
export class PackagesController {
  constructor(private readonly packages: PackagesService) {}

  /**
   * POST /shipments/{awb}/packages — create a package (idempotent). Creates the
   * shipment on the first package; server assigns the number and billing.
   * Replays (same Idempotency-Key / client UUID) return 200; new ones 201.
   */
  @Post(':awb/packages')
  async create(
    @Param('awb') awb: string,
    @Body() dto: PackageCreateDto,
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
    @Res({ passthrough: true }) res: Response,
  ) {
    if (!idempotencyKey) {
      throw new BadRequestException({
        code: 'IDEMPOTENCY_KEY_REQUIRED',
        message: 'Idempotency-Key header is required',
      });
    }
    const { package: pkg, replayed } = await this.packages.create(
      awb,
      dto,
      idempotencyKey,
      user,
      req.ip,
    );
    res.status(replayed ? 200 : 201);
    return pkg;
  }
}
