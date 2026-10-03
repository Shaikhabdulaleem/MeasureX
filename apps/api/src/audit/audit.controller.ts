import { Controller, Get, Query } from '@nestjs/common';
import { Role } from '@prisma/client';
import { AuditService, AuditQuery } from './audit.service';
import { Roles } from '../auth/decorators/roles.decorator';
import { CurrentUser, AuthUser } from '../auth/decorators/current-user.decorator';

/** GET /audit — read the audit log (Team Leader own-branch / Admin scoped). */
@Controller('audit')
export class AuditController {
  constructor(private readonly audit: AuditService) {}

  @Get()
  @Roles(Role.team_leader, Role.admin)
  list(@CurrentUser() user: AuthUser, @Query() query: AuditQuery) {
    return this.audit.list(user, query);
  }
}
