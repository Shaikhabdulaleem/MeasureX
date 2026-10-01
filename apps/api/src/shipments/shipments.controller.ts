import { Controller, Get, HttpCode, HttpStatus, Param, Post, Query, Req } from '@nestjs/common';
import { Request } from 'express';
import { ShipmentsService } from './shipments.service';
import { ShipmentQueryDto } from './dto/shipment-query.dto';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller('shipments')
export class ShipmentsController {
  constructor(private readonly shipments: ShipmentsService) {}

  @Get()
  list(@CurrentUser() user: AuthUser, @Query() query: ShipmentQueryDto) {
    return this.shipments.list(user, query);
  }

  @Get(':awb')
  detail(@Param('awb') awb: string, @CurrentUser() user: AuthUser) {
    return this.shipments.detail(awb, user);
  }

  @Post(':awb/complete')
  @HttpCode(HttpStatus.OK)
  complete(@Param('awb') awb: string, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.shipments.complete(awb, user, req.ip);
  }
}
