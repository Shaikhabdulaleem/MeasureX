import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  ParseUUIDPipe,
  Post,
  Req,
} from '@nestjs/common';
import { Request } from 'express';
import { Role } from '@prisma/client';
import { PackageActionsService } from './package-actions.service';
import { PackageCorrectionDto, PackageVoidDto } from './dto/package-actions.dto';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

/** Team-Leader / Admin actions on an existing package (PRD §8, §11). */
@Controller('packages')
export class PackageActionsController {
  constructor(private readonly actions: PackageActionsService) {}

  /** GET /packages/{id}/versions — full version history (newest first). */
  @Get(':id/versions')
  listVersions(@Param('id', ParseUUIDPipe) id: string, @CurrentUser() user: AuthUser) {
    return this.actions.listVersions(id, user);
  }

  /** POST /packages/{id}/corrections — append a corrected version (reason required). */
  @Post(':id/corrections')
  @Roles(Role.team_leader, Role.admin)
  @HttpCode(HttpStatus.CREATED)
  correct(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: PackageCorrectionDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.actions.correct(id, dto, user, req.ip);
  }

  /** POST /packages/{id}/void — void the package (reason required). */
  @Post(':id/void')
  @Roles(Role.team_leader, Role.admin)
  @HttpCode(HttpStatus.OK)
  void(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: PackageVoidDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.actions.void(id, dto, user, req.ip);
  }
}
