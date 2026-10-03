import { Body, Controller, Get, Param, ParseUUIDPipe, Patch, Post, Query, Req } from '@nestjs/common';
import { Request } from 'express';
import { ScalesService } from './scales.service';
import { ScaleCreateDto, ScaleUpdateDto } from './dto/scale.dto';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller('scales')
export class ScalesController {
  constructor(private readonly scales: ScalesService) {}

  /**
   * GET /scales — the approved-model list mobile binds to. Any authenticated
   * user may read it (Labour needs it to select a scale); `?all=true` (Admin UI)
   * includes unapproved models.
   */
  @Get()
  list(@Query('all') all: string | undefined, @CurrentUser() user: AuthUser) {
    const includeAll = all === 'true' && user.role === 'admin';
    return this.scales.list(!includeAll);
  }

  @Get(':id')
  get(@Param('id', ParseUUIDPipe) id: string) {
    return this.scales.get(id);
  }

  /** POST /scales — register a scale model (Admin only). */
  @Post()
  @Roles('admin')
  create(@Body() dto: ScaleCreateDto, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.scales.create(dto, user, req.ip);
  }

  /** PATCH /scales/{id} — mark approved / tune thresholds (Admin only). */
  @Patch(':id')
  @Roles('admin')
  update(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: ScaleUpdateDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.scales.update(id, dto, user, req.ip);
  }
}
