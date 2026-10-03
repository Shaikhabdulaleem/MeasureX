import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  ParseUUIDPipe,
  Patch,
  Post,
  Query,
  Req,
} from '@nestjs/common';
import { Request } from 'express';
import { Role } from '@prisma/client';
import { UsersService } from './users.service';
import { UserCreateDto, UserResetPasswordDto, UserUpdateDto } from './dto/user.dto';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

/** Admin user management (PRD §3, §11). Every mutation is audited. */
@Controller('users')
@Roles(Role.admin)
export class UsersController {
  constructor(private readonly users: UsersService) {}

  @Get()
  list(
    @CurrentUser() user: AuthUser,
    @Query('branchId') branchId?: string,
    @Query('role') role?: Role,
    @Query('status') status?: string,
  ) {
    return this.users.list(user, { branchId, role, status });
  }

  @Get(':id')
  get(@Param('id', ParseUUIDPipe) id: string, @CurrentUser() user: AuthUser) {
    return this.users.get(id, user);
  }

  @Post()
  @HttpCode(HttpStatus.CREATED)
  create(@Body() dto: UserCreateDto, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.users.create(dto, user, req.ip);
  }

  @Patch(':id')
  update(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: UserUpdateDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.users.update(id, dto, user, req.ip);
  }

  @Post(':id/reset-password')
  @HttpCode(HttpStatus.OK)
  resetPassword(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: UserResetPasswordDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.users.resetPassword(id, dto, user, req.ip);
  }

  @Post(':id/unlock')
  @HttpCode(HttpStatus.OK)
  unlock(
    @Param('id', ParseUUIDPipe) id: string,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.users.unlock(id, user, req.ip);
  }
}
