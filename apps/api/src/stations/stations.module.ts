import { Module } from '@nestjs/common';
import {
  Body,
  ConflictException,
  Controller,
  Get,
  Injectable,
  NotFoundException,
  Param,
  ParseUUIDPipe,
  Patch,
  Post,
  Query,
  Req,
} from '@nestjs/common';
import { IsInt, IsOptional, IsString, IsUUID, Min, MinLength } from 'class-validator';
import { Request } from 'express';
import { Prisma, Role, Station } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

// --- DTOs -------------------------------------------------------------------

export class StationCreateDto {
  @IsString()
  @MinLength(1)
  code!: string;

  @IsUUID()
  branchId!: string;

  @IsInt()
  @Min(1)
  matSizeMm!: number;

  @IsInt()
  @Min(1)
  markerSizeMm!: number;

  @IsOptional()
  @IsUUID()
  scaleId?: string;
}

export class StationUpdateDto {
  @IsOptional()
  @IsInt()
  @Min(1)
  matSizeMm?: number;

  @IsOptional()
  @IsInt()
  @Min(1)
  markerSizeMm?: number;

  @IsOptional()
  @IsUUID()
  scaleId?: string | null;
}

function serializeStation(s: Station) {
  return {
    id: s.id,
    code: s.code,
    branchId: s.branchId,
    matSizeMm: s.matSizeMm,
    markerSizeMm: s.markerSizeMm,
    scaleId: s.scaleId,
  };
}

// --- Service ----------------------------------------------------------------

@Injectable()
export class StationsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  async list(branchId?: string) {
    const where: Prisma.StationWhereInput = { deletedAt: null };
    if (branchId) where.branchId = branchId;
    const rows = await this.prisma.station.findMany({ where, orderBy: { code: 'asc' } });
    return { items: rows.map(serializeStation) };
  }

  async create(dto: StationCreateDto, actor: AuthUser, ip?: string) {
    const dup = await this.prisma.station.findUnique({ where: { code: dto.code } });
    if (dup) {
      throw new ConflictException({ code: 'STATION_CODE_TAKEN', message: 'Station code exists' });
    }
    const station = await this.prisma.station.create({
      data: {
        code: dto.code,
        branchId: dto.branchId,
        matSizeMm: dto.matSizeMm,
        markerSizeMm: dto.markerSizeMm,
        scaleId: dto.scaleId ?? null,
      },
    });
    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'station',
      entityId: station.id,
      action: 'station_created',
      after: serializeStation(station),
      ip,
    });
    return serializeStation(station);
  }

  async update(id: string, dto: StationUpdateDto, actor: AuthUser, ip?: string) {
    const before = await this.findOrThrow(id);
    const station = await this.prisma.station.update({
      where: { id },
      data: {
        ...(dto.matSizeMm !== undefined ? { matSizeMm: dto.matSizeMm } : {}),
        ...(dto.markerSizeMm !== undefined ? { markerSizeMm: dto.markerSizeMm } : {}),
        ...(dto.scaleId !== undefined ? { scaleId: dto.scaleId } : {}),
      },
    });
    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'station',
      entityId: id,
      action: 'station_updated',
      before: serializeStation(before),
      after: serializeStation(station),
      ip,
    });
    return serializeStation(station);
  }

  private async findOrThrow(id: string): Promise<Station> {
    const station = await this.prisma.station.findFirst({ where: { id, deletedAt: null } });
    if (!station) throw new NotFoundException({ code: 'NOT_FOUND', message: 'Station not found' });
    return station;
  }
}

// --- Controller -------------------------------------------------------------

@Controller('stations')
export class StationsController {
  constructor(private readonly stations: StationsService) {}

  /** Any authenticated user may read stations (mobile binds a station). */
  @Get()
  list(@Query('branchId') branchId?: string) {
    return this.stations.list(branchId);
  }

  @Post()
  @Roles(Role.admin)
  create(@Body() dto: StationCreateDto, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.stations.create(dto, user, req.ip);
  }

  @Patch(':id')
  @Roles(Role.admin)
  update(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: StationUpdateDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.stations.update(id, dto, user, req.ip);
  }
}

@Module({
  controllers: [StationsController],
  providers: [StationsService],
})
export class StationsModule {}
