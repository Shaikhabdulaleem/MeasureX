import { Body, Controller, HttpCode, HttpStatus, Post } from '@nestjs/common';
import { EventsService } from './events.service';
import { EventBatchDto } from './dto/event.dto';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

@Controller('events')
export class EventsController {
  constructor(private readonly events: EventsService) {}

  /** POST /events/batch — upload measurement telemetry (append-only). */
  @Post('batch')
  @HttpCode(HttpStatus.ACCEPTED)
  batch(@Body() dto: EventBatchDto, @CurrentUser() user: AuthUser) {
    return this.events.batch(dto, user);
  }
}
