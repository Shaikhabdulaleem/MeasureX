import { Injectable } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { EventBatchDto } from './dto/event.dto';

@Injectable()
export class EventsService {
  constructor(private readonly prisma: PrismaService) {}

  /**
   * POST /events/batch — append telemetry (PRD §12, §13). `createMany` with
   * `skipDuplicates` keyed on the client UUID makes a replayed batch a no-op, so
   * the mobile app can resend freely. The caller's id is the default userId when
   * an item omits one. Returns how many rows were newly inserted.
   */
  async batch(dto: EventBatchDto, user: AuthUser): Promise<{ inserted: number }> {
    const data: Prisma.MeasurementEventCreateManyInput[] = dto.events.map((e) => ({
      ...(e.id ? { id: e.id } : {}),
      deviceId: e.deviceId ?? null,
      userId: e.userId ?? user.sub,
      awb: e.awb ?? null,
      type: e.type,
      payload: (e.payload ?? undefined) as Prisma.InputJsonValue,
      occurredAt: new Date(e.occurredAt),
    }));

    const result = await this.prisma.measurementEvent.createMany({
      data,
      skipDuplicates: true,
    });
    return { inserted: result.count };
  }
}
