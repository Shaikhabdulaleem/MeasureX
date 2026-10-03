import { Module } from '@nestjs/common';
import { PackagesController } from './packages.controller';
import { PackagesService } from './packages.service';
import { PackageActionsController } from './package-actions.controller';
import { PackageActionsService } from './package-actions.service';
import { ScalesModule } from '../scales/scales.module';

@Module({
  imports: [ScalesModule],
  controllers: [PackagesController, PackageActionsController],
  providers: [PackagesService, PackageActionsService],
  exports: [PackagesService],
})
export class PackagesModule {}
