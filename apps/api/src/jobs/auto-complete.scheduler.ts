import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { Queue, Worker } from 'bullmq';
import IORedis, { Redis } from 'ioredis';
import { AutoCompleteService } from './auto-complete.service';

const QUEUE_NAME = 'measurex-maintenance';
const JOB_NAME = 'idle-auto-complete';
/** How often the scan runs; the idle threshold itself is config-driven. */
const SCAN_EVERY_MS = 60_000;

/**
 * Wires the idle auto-complete scan onto a BullMQ repeatable job (PRD §5, §14).
 * Disabled in tests and whenever REDIS_URL is unset, so the API and CI run
 * without Redis; the underlying service is always available and tested directly.
 * Any Redis failure is logged and never crashes the API.
 */
@Injectable()
export class AutoCompleteScheduler implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(AutoCompleteScheduler.name);
  private connection?: Redis;
  private queue?: Queue;
  private worker?: Worker;

  constructor(private readonly autoComplete: AutoCompleteService) {}

  async onModuleInit(): Promise<void> {
    if (process.env.NODE_ENV === 'test') return;
    const url = process.env.REDIS_URL;
    if (!url) {
      this.logger.warn('REDIS_URL not set — idle auto-complete scheduler disabled.');
      return;
    }

    try {
      // bullmq requires maxRetriesPerRequest = null on the worker connection.
      this.connection = new IORedis(url, { maxRetriesPerRequest: null });
      this.queue = new Queue(QUEUE_NAME, { connection: this.connection });
      await this.queue.add(
        JOB_NAME,
        {},
        {
          repeat: { every: SCAN_EVERY_MS },
          removeOnComplete: true,
          removeOnFail: 50,
          jobId: JOB_NAME,
        },
      );
      this.worker = new Worker(
        QUEUE_NAME,
        async () => {
          await this.autoComplete.completeIdleShipments();
        },
        { connection: this.connection },
      );
      this.worker.on('failed', (_job, err) => {
        this.logger.error(`Auto-complete job failed: ${err?.message}`);
      });
      this.logger.log('Idle auto-complete scheduler started.');
    } catch (err) {
      this.logger.error(`Could not start auto-complete scheduler: ${(err as Error).message}`);
    }
  }

  async onModuleDestroy(): Promise<void> {
    await this.worker?.close();
    await this.queue?.close();
    this.connection?.disconnect();
  }
}
