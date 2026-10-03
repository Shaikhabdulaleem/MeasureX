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
import { ReviewService } from './review.service';
import { FlagCreateDto, FlagQueryDto, FlagResolveDto, RemeasureCreateDto } from './dto/review.dto';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller()
export class ReviewController {
  constructor(private readonly review: ReviewService) {}

  /** GET /flags — the review queue (Team Leader / Admin), branch-scoped. */
  @Get('flags')
  @Roles(Role.team_leader, Role.admin)
  listFlags(@CurrentUser() user: AuthUser, @Query() query: FlagQueryDto) {
    return this.review.listFlags(user, query);
  }

  /** POST /flags/{id}/resolve — approve / dismiss a flag (Team Leader / Admin). */
  @Post('flags/:id/resolve')
  @Roles(Role.team_leader, Role.admin)
  @HttpCode(HttpStatus.OK)
  resolveFlag(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: FlagResolveDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.review.resolveFlag(id, dto, user, req.ip);
  }

  /** POST /flags — "Flag for Team Leader" (any authenticated role, incl. Labour). */
  @Post('flags')
  @HttpCode(HttpStatus.CREATED)
  createFlag(@Body() dto: FlagCreateDto, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.review.createFlag(dto, user, req.ip);
  }

  /** GET /remeasurements — list requests in scope (Team Leader / Admin). */
  @Get('remeasurements')
  @Roles(Role.team_leader, Role.admin)
  listRemeasurements(
    @CurrentUser() user: AuthUser,
    @Query('status') status: string | undefined,
    @Query('cursor') cursor: string | undefined,
  ) {
    return this.review.listRemeasurements(user, status, cursor);
  }

  /** POST /remeasurements — request a remeasurement (Team Leader / Admin). */
  @Post('remeasurements')
  @Roles(Role.team_leader, Role.admin)
  @HttpCode(HttpStatus.CREATED)
  createRemeasure(
    @Body() dto: RemeasureCreateDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.review.createRemeasure(dto, user, req.ip);
  }

  /** POST /remeasurements/{id}/cancel — cancel an open request (Team Leader / Admin). */
  @Post('remeasurements/:id/cancel')
  @Roles(Role.team_leader, Role.admin)
  @HttpCode(HttpStatus.OK)
  cancelRemeasure(@Param('id') id: string, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.review.cancelRemeasure(id, user, req.ip);
  }
}
