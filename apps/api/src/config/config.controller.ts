import { Body, Controller, Get, Put, Req } from '@nestjs/common';
import { Request } from 'express';
import { Role } from '@prisma/client';
import { ConfigService, EffectiveConfig } from './config.service';
import { ConfigUpdateDto } from './dto/config-update.dto';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

/** Global configuration (PRD §11, §14). Read by any authenticated user; writes are Admin. */
@Controller('config')
export class ConfigController {
  constructor(private readonly config: ConfigService) {}

  @Get()
  get(): Promise<EffectiveConfig> {
    return this.config.getEffectiveConfig();
  }

  @Put()
  @Roles(Role.admin)
  update(
    @Body() dto: ConfigUpdateDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ): Promise<EffectiveConfig> {
    return this.config.updateConfig(dto, user, req.ip);
  }
}
