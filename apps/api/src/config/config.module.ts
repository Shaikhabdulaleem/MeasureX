import { Global, Module } from '@nestjs/common';
import { ConfigService } from './config.service';
import { ConfigController } from './config.controller';

/**
 * Global so any feature module can read effective configuration without
 * re-importing. Backed by the `config` table (PRD §12); defaults live in
 * ConfigService.
 */
@Global()
@Module({
  controllers: [ConfigController],
  providers: [ConfigService],
  exports: [ConfigService],
})
export class ConfigModule {}
