import {
  BadRequestException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../audit/audit.service';
import { AuthUser } from '../auth/decorators/current-user.decorator';
import { serializePhoto } from '../common/serializers';
import { shipmentScopeWhere } from '../common/scope';
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
   * URL. The client uploads the JPEG directly to the private bucket; the bytes
   * never pass through the API. Authorised for the worker who measured the
   * package, or a Team Leader / Admin whose scope covers the package's shipment
   * (PRD §3, §6). The request is audited (photo_upload_requested).
   */
  async createUploadTarget(
    packageId: string,
    dto: PhotoUploadRequestDto,
    user: AuthUser,
    ip?: string,
  ) {
    if (!dto.contentType.startsWith('image/')) {
      throw new BadRequestException({
        code: 'INVALID_CONTENT_TYPE',
        message: 'Only image uploads are allowed',
      });
    }

    const pkg = await this.prisma.package.findFirst({
      where: { id: packageId, deletedAt: null },
      select: { id: true, currentVersionId: true, measuredBy: true, shipmentId: true },
    });
    if (!pkg) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Package not found' });
    }

    await this.assertCanAttach(pkg.measuredBy, pkg.shipmentId, user);

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

    await this.audit.record({
      userId: user.sub,
      role: user.role as never,
      entity: 'photo',
      entityId: photo.id,
      action: 'photo_upload_requested',
      ip,
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
   * GET /photos/{id} — short-lived signed view URL. Team Leader / Admin only
   * (enforced at the controller) AND only for a photo whose shipment is within
   * the caller's branch scope (PRD §3, §6). Out of scope → 404. The view is
   * logged (photo_viewed).
   */
  async getViewUrl(photoId: string, user: AuthUser, ip?: string): Promise<PresignedView> {
    const photo = await this.prisma.photo.findFirst({
      where: { id: photoId, deletedAt: null },
      include: { package: { select: { shipmentId: true } } },
    });
    if (!photo) {
      throw new NotFoundException({ code: 'NOT_FOUND', message: 'Photo not found' });
    }

    // Branch/role scope: the photo's shipment must be visible to this user.
    const inScope = await this.prisma.shipment.findFirst({
      where: { AND: [{ id: photo.package.shipmentId }, shipmentScopeWhere(user)] },
      select: { id: true },
    });
    if (!inScope) {
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

  // --- internals -----------------------------------------------------------

  private async assertCanAttach(
    measuredBy: string | null,
    shipmentId: string,
    user: AuthUser,
  ): Promise<void> {
    if (measuredBy && measuredBy === user.sub) return; // the measurer
    if (user.role === 'team_leader' || user.role === 'admin') {
      const inScope = await this.prisma.shipment.findFirst({
        where: { AND: [{ id: shipmentId }, shipmentScopeWhere(user)] },
        select: { id: true },
      });
      if (inScope) return;
    }
    throw new ForbiddenException({
      code: 'FORBIDDEN',
      message: 'Not allowed to attach a photo to this package',
    });
  }
}
