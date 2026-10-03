import { Module } from '@nestjs/common';
import { Body, Controller, Get, Param, ParseUUIDPipe, Patch, Post, Req } from '@nestjs/common';
import { IsIn, IsOptional, IsString, MinLength } from 'class-validator';
import { Request } from 'express';
import { Branch, Role } from '@prisma/client';
import { ConflictException, Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

// --- DTOs -------------------------------------------------------------------

export class BranchCreateDto {
  @IsString()
  @MinLength(1)
  code!: string;

  @IsString()
  @MinLength(1)
  name!: string;
}

export class BranchUpdateDto {
  @IsOptional()
  @IsString()
  @MinLength(1)
  name?: string;

  @IsOptional()
  @IsIn(['active', 'inactive'])
  status?: 'active' | 'inactive';
}

function serializeBranch(b: Branch) {
  return {
    id: b.id,
    code: b.code,
    name: b.name,
    status: b.status,
    createdAt: b.createdAt.toISOString(),
    updatedAt: b.updatedAt.toISOString(),
  };
}

// --- Service ----------------------------------------------------------------

@Injectable()
export class BranchesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  async list() {
    const rows = await this.prisma.branch.findMany({
      where: { deletedAt: null },
      orderBy: { code: 'asc' },
    });
    return { items: rows.map(serializeBranch) };
  }

  async create(dto: BranchCreateDto, actor: AuthUser, ip?: string) {
    const dup = await this.prisma.branch.findUnique({ where: { code: dto.code } });
    if (dup) {
      throw new ConflictException({ code: 'BRANCH_CODE_TAKEN', message: 'Branch code exists' });
    }
    const branch = await this.prisma.branch.create({
      data: { code: dto.code, name: dto.name, status: 'active' },
    });
    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'branch',
      entityId: branch.id,
      action: 'branch_created',
      after: serializeBranch(branch),
      ip,
    });
    return serializeBranch(branch);
  }

  async update(id: string, dto: BranchUpdateDto, actor: AuthUser, ip?: string) {
    const before = await this.findOrThrow(id);
    const branch = await this.prisma.branch.update({
      where: { id },
      data: {
        ...(dto.name !== undefined ? { name: dto.name } : {}),
        ...(dto.status !== undefined ? { status: dto.status } : {}),
      },
    });
    await this.audit.record({
      userId: actor.sub,
      role: actor.role as never,
      entity: 'branch',
      entityId: id,
      action: 'branch_updated',
      before: serializeBranch(before),
      after: serializeBranch(branch),
      ip,
    });
    return serializeBranch(branch);
  }

  private async findOrThrow(id: string): Promise<Branch> {
    const branch = await this.prisma.branch.findFirst({ where: { id, deletedAt: null } });
    if (!branch) throw new NotFoundException({ code: 'NOT_FOUND', message: 'Branch not found' });
    return branch;
  }
}

// --- Controller -------------------------------------------------------------

@Controller('branches')
export class BranchesController {
  constructor(private readonly branches: BranchesService) {}

  /** Any authenticated user may read the branch list (needed for display). */
  @Get()
  list() {
    return this.branches.list();
  }

  @Post()
  @Roles(Role.admin)
  create(@Body() dto: BranchCreateDto, @CurrentUser() user: AuthUser, @Req() req: Request) {
    return this.branches.create(dto, user, req.ip);
  }

  @Patch(':id')
  @Roles(Role.admin)
  update(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() dto: BranchUpdateDto,
    @CurrentUser() user: AuthUser,
    @Req() req: Request,
  ) {
    return this.branches.update(id, dto, user, req.ip);
  }
}

@Module({
  controllers: [BranchesController],
  providers: [BranchesService],
})
export class BranchesModule {}
