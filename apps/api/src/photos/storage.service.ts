import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import {
  CreateBucketCommand,
  GetObjectCommand,
  HeadBucketCommand,
  PutObjectCommand,
  S3Client,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

/** TTLs for signed URLs (seconds). Views are kept short-lived (PRD §6, §14). */
const UPLOAD_TTL_SECONDS = 900;
const VIEW_TTL_SECONDS = 300;

export interface PresignedUpload {
  url: string;
  method: 'PUT';
  headers: Record<string, string>;
  expiresAt: string;
}

export interface PresignedView {
  url: string;
  expiresAt: string;
}

/**
 * Thin wrapper over an S3-compatible store (MinIO locally; a Saudi-region bucket
 * in production — PRD §14). The bucket is PRIVATE: files are only ever reached
 * through short-lived signed URLs. Presigning is offline, so the e2e tests do
 * not need a running MinIO.
 */
@Injectable()
export class StorageService implements OnModuleInit {
  private readonly logger = new Logger(StorageService.name);
  private readonly client: S3Client;
  readonly bucket: string;

  constructor() {
    this.bucket = process.env.S3_BUCKET ?? 'measurex-photos';
    this.client = new S3Client({
      region: process.env.S3_REGION ?? 'us-east-1',
      endpoint: process.env.S3_ENDPOINT ?? 'http://localhost:9000',
      forcePathStyle: (process.env.S3_FORCE_PATH_STYLE ?? 'true') === 'true',
      credentials: {
        accessKeyId: process.env.S3_ACCESS_KEY ?? 'minioadmin',
        secretAccessKey: process.env.S3_SECRET_KEY ?? 'minioadmin',
      },
    });
  }

  async onModuleInit(): Promise<void> {
    if (process.env.NODE_ENV === 'test') return;
    // Best effort: create the private bucket if it is missing. Never fatal.
    try {
      await this.client.send(new HeadBucketCommand({ Bucket: this.bucket }));
    } catch {
      try {
        await this.client.send(new CreateBucketCommand({ Bucket: this.bucket }));
        this.logger.log(`Created photo bucket "${this.bucket}".`);
      } catch (err) {
        this.logger.warn(`Could not ensure bucket "${this.bucket}": ${(err as Error).message}`);
      }
    }
  }

  photoKey(packageId: string, photoId: string): string {
    return `packages/${packageId}/${photoId}.jpg`;
  }

  async presignUpload(key: string, contentType: string): Promise<PresignedUpload> {
    const command = new PutObjectCommand({
      Bucket: this.bucket,
      Key: key,
      ContentType: contentType,
    });
    const url = await getSignedUrl(this.client, command, { expiresIn: UPLOAD_TTL_SECONDS });
    return {
      url,
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      expiresAt: new Date(Date.now() + UPLOAD_TTL_SECONDS * 1000).toISOString(),
    };
  }

  async presignView(key: string): Promise<PresignedView> {
    const command = new GetObjectCommand({ Bucket: this.bucket, Key: key });
    const url = await getSignedUrl(this.client, command, { expiresIn: VIEW_TTL_SECONDS });
    return {
      url,
      expiresAt: new Date(Date.now() + VIEW_TTL_SECONDS * 1000).toISOString(),
    };
  }
}
