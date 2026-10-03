import { Module } from '@nestjs/common';
import { ScalesController } from './scales.controller';
import { ScalesService } from './scales.service';

@Module({
  controllers: [ScalesController],
  providers: [ScalesService],
  exports: [ScalesService],
})
export class ScalesModule {}
