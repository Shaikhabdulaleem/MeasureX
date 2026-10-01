import { Global, Module } from '@nestjs/common';
import { ConfigService } from './config.service';

/**
 * Global so any feature module can read effective configuration without
 * re-importing. Backed by the `config` table (PRD §12); defaults live in
 * ConfigService.
 */
@Global()
@Module({
  providers: [ConfigService],
  exports: [ConfigService],
})
export class ConfigModule {}
