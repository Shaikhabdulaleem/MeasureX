import { Controller, Get, Param } from '@nestjs/common';
import { LookupService } from './lookup.service';

@Controller('awb')
export class LookupController {
  constructor(private readonly lookup: LookupService) {}

  /**
   * GET /awb/{awb}/lookup — existing MeasureX shipment + packages for an AWB.
   * Any authenticated role (the scanner's history check). Returns found=false
   * for a new AWB rather than 404, so the capture flow continues smoothly.
   */
  @Get(':awb/lookup')
  lookupAwb(@Param('awb') awb: string) {
    return this.lookup.lookup(awb);
  }
}
