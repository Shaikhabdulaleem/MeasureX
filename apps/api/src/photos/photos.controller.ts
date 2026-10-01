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

  /** POST /packages/{id}/photos — signed upload target. Any authenticated role. */
  @Post('packages/:id/photos')
  @HttpCode(HttpStatus.CREATED)
  createUploadTarget(@Param('id') id: string, @Body() dto: PhotoUploadRequestDto) {
    return this.photos.createUploadTarget(id, dto);
  }

  /** GET /photos/{id} — signed view URL. Team Leader / Admin only; view logged. */
  @Get('photos/:id')
  @Roles(Role.team_leader, Role.admin)
  getViewUrl(@Param('id') id: string, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.photos.getViewUrl(id, user, req.ip);
  }
}
