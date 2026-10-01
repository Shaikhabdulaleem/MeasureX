import { Module } from '@nestjs/common';
import { AutoCompleteService } from './auto-complete.service';
import { AutoCompleteScheduler } from './auto-complete.scheduler';

/**
 * Background maintenance. The scheduler self-disables without Redis / in tests;
 * AutoCompleteService is exported for direct use (and testing).
 */
@Module({
  providers: [AutoCompleteService, AutoCompleteScheduler],
  exports: [AutoCompleteService],
})
export class JobsModule {}
