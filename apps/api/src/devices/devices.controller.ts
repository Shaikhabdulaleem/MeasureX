import { Body, Controller, Get, HttpCode, HttpStatus, Post } from '@nestjs/common';
import { DevicesService } from './devices.service';
import { DeviceRegisterDto } from './dto/device.dto';
import { ConfigService, EffectiveConfig } from '../config/config.service';
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
}
