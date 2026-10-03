import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { JwtModule } from '@nestjs/jwt';
import { PrismaModule } from './prisma/prisma.module';
import { AuditModule } from './audit/audit.module';
import { AuthModule } from './auth/auth.module';
import { HealthModule } from './health/health.module';
import { ConfigModule } from './config/config.module';
import { DevicesModule } from './devices/devices.module';
import { LookupModule } from './lookup/lookup.module';
import { PackagesModule } from './packages/packages.module';
import { ShipmentsModule } from './shipments/shipments.module';
import { PhotosModule } from './photos/photos.module';
import { ReviewModule } from './review/review.module';
import { ScalesModule } from './scales/scales.module';
import { SyncModule } from './sync/sync.module';
import { EventsModule } from './events/events.module';
import { JobsModule } from './jobs/jobs.module';
import { UsersModule } from './users/users.module';
import { BranchesModule } from './branches/branches.module';
import { StationsModule } from './stations/stations.module';
import { ReportsModule } from './reports/reports.module';
import { DashboardModule } from './dashboard/dashboard.module';
import { JwtAuthGuard } from './auth/guards/jwt-auth.guard';
import { PasswordChangeGuard } from './auth/guards/password-change.guard';
import { RolesGuard } from './auth/guards/roles.guard';

@Module({
  imports: [
    JwtModule.register({}),
    PrismaModule,
    AuditModule,
    AuthModule,
    HealthModule,
    ConfigModule,
    DevicesModule,
    LookupModule,
    PackagesModule,
    ShipmentsModule,
    PhotosModule,
    ReviewModule,
    ScalesModule,
    SyncModule,
    EventsModule,
    JobsModule,
    UsersModule,
    BranchesModule,
    StationsModule,
    ReportsModule,
    DashboardModule,
  ],
  providers: [
    // Order matters: authenticate → enforce forced password change → roles.
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_GUARD, useClass: PasswordChangeGuard },
    { provide: APP_GUARD, useClass: RolesGuard },
  ],
})
export class AppModule {}
