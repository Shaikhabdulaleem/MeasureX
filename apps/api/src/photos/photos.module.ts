import { Module } from '@nestjs/common';
import { PhotosController } from './photos.controller';
import { PhotosService } from './photos.service';
import { StorageService } from './storage.service';

@Module({
  controllers: [PhotosController],
  providers: [PhotosService, StorageService],
  exports: [StorageService],
})
export class PhotosModule {}
