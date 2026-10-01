import { Body, Controller, HttpCode, HttpStatus, Param, Post, Req } from '@nestjs/common';
import { Request } from 'express';
import { Role } from '@prisma/client';
import { ReviewService } from './review.service';
import { FlagCreateDto, RemeasureCreateDto } from './dto/review.dto';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller()
export class ReviewController {
  constructor(private readonly review: ReviewService) {}

  /** POST /flags — "Flag for Team Leader" (any authenticated role, incl. Labour). */
  @Post('flags')
  @HttpCode(HttpStatus.CREATED)
  createFlag(@Body() dto: FlagCreateDto, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.review.createFlag(dto, user, req.ip);
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
