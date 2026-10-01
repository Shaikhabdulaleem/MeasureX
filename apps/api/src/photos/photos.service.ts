import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { serializePhoto } from '../common/serializers';
import { StorageService, PresignedView } from './storage.service';
import { PhotoUploadRequestDto } from './dto/photo.dto';

@Injectable()
export class PhotosService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly storage: StorageService,
    private readonly audit: AuditService,
  ) {}

  /**
   * POST /packages/{id}/photos — create the photo record and return a signed PUT
   * URL. The client uploads the JPEG directly to the private bucket. The bytes
   * never pass through the API.
   */
  async createUploadTarget(packageId: string, dto: PhotoUploadRequestDto) {
    if (!dto.contentType.startsWith('image/')) {
      throw new BadRequestException({
        code: 'INVALID_CONTENT_TYPE',
        message: 'Only image uploads are allowed',
      });
    }

    const pkg = await this.prisma.package.findFirst({
      where: { id: packageId, deletedAt: null },
      select: { id: true, currentVersionId: true },
    });
    if (!pkg) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Package not found' });
    }

    const photoId = crypto.randomUUID();
    const key = this.storage.photoKey(packageId, photoId);

    const photo = await this.prisma.photo.create({
      data: {
        id: photoId,
        packageId,
        versionId: pkg.currentVersionId,
        kind: dto.kind ?? 'raw',
        storageKey: key,
        bytes: dto.bytes ?? null,
        width: dto.width ?? null,
        height: dto.height ?? null,
      },
    });

    const target = await this.storage.presignUpload(key, dto.contentType);
    return {
      photoId: photo.id,
      uploadUrl: target.url,
      method: target.method,
      headers: target.headers,
      expiresAt: target.expiresAt,
      photo: serializePhoto(photo),
    };
  }

  /**
   * GET /photos/{id} — short-lived signed view URL. Team Leader / Admin only;
   * the view is logged (PRD §6, §14). Role is enforced at the controller.
   */
  async getViewUrl(photoId: string, user: AuthUser, ip?: string): Promise<PresignedView> {
    const photo = await this.prisma.photo.findFirst({
      where: { id: photoId, deletedAt: null },
    });
    if (!photo) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Photo not found' });
    }

    const signed = await this.storage.presignView(photo.storageKey);

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'photo',
      entityId: photo.id,
      action: 'photo_viewed',
      ip,
    });

    return signed;
  }
}
