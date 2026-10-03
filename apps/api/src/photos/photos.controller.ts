import { Body, Controller, Get, HttpCode, HttpStatus, Param, Post, Req } from '@nestjs/common';
import { Request } from 'express';
import { Role } from '@prisma/client';
import { PhotosService } from './photos.service';
import { PhotoUploadRequestDto } from './dto/photo.dto';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller()
export class PhotosController {
  constructor(private readonly photos: PhotosService) {}

  /**
   * POST /packages/{id}/photos — signed upload target. Allowed for the worker
   * who measured the package, or a TL/Admin whose scope covers its shipment.
   */
  @Post('packages/:id/photos')
  @HttpCode(HttpStatus.CREATED)
  createUploadTarget(
    @Param('id') id: string,
    @Body() dto: PhotoUploadRequestDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.photos.createUploadTarget(id, dto, user, req.ip);
  }

  /**
   * POST /photos/{id}/upload-url — a fresh signed PUT URL for an EXISTING photo
   * (retry path; no new row). Allowed for the measurer or a scoped TL/Admin.
   */
  @Post('photos/:id/upload-url')
  @HttpCode(HttpStatus.OK)
  refreshUploadUrl(@Param('id') id: string, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.photos.refreshUploadUrl(id, user, req.ip);
  }

  /** GET /photos/{id} — signed view URL. Team Leader / Admin only; view logged. */
  @Get('photos/:id')
  @Roles(Role.team_leader, Role.admin)
  getViewUrl(@Param('id') id: string, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.photos.getViewUrl(id, user, req.ip);
  }
}
