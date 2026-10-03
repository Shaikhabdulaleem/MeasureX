import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  ParseUUIDPipe,
  Post,
  Query,
  Req,
} from '@nestjs/common';
import { Request } from 'express';
import { Role } from '@prisma/client';
import { DevicesService } from './devices.service';
import { DeviceRegisterDto, DeviceBlockDto } from './dto/device.dto';
import { ConfigService, EffectiveConfig } from '../config/config.service';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller('devices')
export class DevicesController {
  constructor(
    private readonly devices: DevicesService,
    private readonly config: ConfigService,
  ) {}

  @Post('register')
  @HttpCode(HttpStatus.OK)
  register(@Body() dto: DeviceRegisterDto, @CurrentUser() user: AuthUser) {
    return this.devices.register(dto, user);
  }

  /** GET /devices/me/config — effective config (divisor, step, AWB regex, limits). */
  @Get('me/config')
  getConfig(): Promise<EffectiveConfig> {
    return this.config.getEffectiveConfig();
  }

  /** GET /devices — Admin device inventory (PRD §11). */
  @Get()
  @Roles(Role.admin)
  list(@Query('blocked') blocked?: string, @Query('tier') tier?: string) {
    return this.devices.list({ blocked, tier });
  }

  /** POST /devices/{id}/block — block / unblock a device (Admin, PRD §10). */
  @Post(':id/block')
  @Roles(Role.admin)
  @HttpCode(HttpStatus.OK)
  setBlocked(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: DeviceBlockDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.devices.setBlocked(id, dto.blocked ?? true, user, req.ip);
  }
}
