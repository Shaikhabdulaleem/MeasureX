import { Prisma } from '@prisma/client';

// Prisma payload shapes used across the shipment/package endpoints.
export const versionInclude = {} satisfies Prisma.MeasurementVersionDefaultArgs['include'];

export type VersionRow = Prisma.MeasurementVersionGetPayload<object>;
export type PhotoRow = Prisma.PhotoGetPayload<object>;
export type PackageRow = Prisma.PackageGetPayload<{
  include: { currentVersion: true; photos: true };
}>;
export type ShipmentRow = Prisma.ShipmentGetPayload<object>;
export type ShipmentDetailRow = Prisma.ShipmentGetPayload<{
  include: { packages: { include: { currentVersion: true; photos: true } } };
}>;

export function serializeVersion(v: VersionRow) {
  return {
    id: v.id,
    packageId: v.packageId,
    versionNo: v.versionNo,
    lengthMm: v.lengthMm,
    widthMm: v.widthMm,
    heightMm: v.heightMm,
    actualWeightG: v.actualWeightG,
    weightSource: v.weightSource,
    scaleId: v.scaleId,
    method: v.method,
    confidence: v.confidence,
    confidenceDetail: v.confidenceDetail ?? null,
    divisorUsed: v.divisorUsed,
    billingLCm: v.billingLCm,
    billingWCm: v.billingWCm,
    billingHCm: v.billingHCm,
    cbm: Number(v.cbm),
    volumetricG: v.volumetricG,
    chargeableG: v.chargeableG,
    createdBy: v.createdBy,
    reason: v.reason,
    createdAt: v.createdAt.toISOString(),
  };
}

export function serializePhoto(p: PhotoRow) {
  return {
    id: p.id,
    packageId: p.packageId,
    versionId: p.versionId,
    kind: p.kind,
    width: p.width,
    height: p.height,
    bytes: p.bytes,
  };
}

export function serializePackage(pkg: PackageRow) {
  return {
    id: pkg.id,
    shipmentId: pkg.shipmentId,
    packageNumber: pkg.packageNumber,
    provisionalNumber: pkg.provisionalNumber,
    status: pkg.status,
    stationId: pkg.stationId,
    deviceId: pkg.deviceId,
    measuredBy: pkg.measuredBy,
    confirmedAt: pkg.confirmedAt?.toISOString() ?? null,
    syncReceivedAt: pkg.syncReceivedAt?.toISOString() ?? null,
    currentVersion: pkg.currentVersion ? serializeVersion(pkg.currentVersion) : null,
    photos: (pkg.photos ?? []).map(serializePhoto),
  };
}

export function serializeShipment(s: ShipmentRow) {
  return {
    id: s.id,
    awb: s.awb,
    branchId: s.branchId,
    clientId: s.clientId,
    status: s.status,
    flags: s.flags,
    totals: {
      pieces: s.totalPieces,
      cbm: Number(s.totalCbm),
      actualG: s.totalActualG,
      volumetricG: s.totalVolumetricG,
      chargeableG: s.totalChargeableG,
    },
    completedAt: s.completedAt?.toISOString() ?? null,
    createdAt: s.createdAt.toISOString(),
    updatedAt: s.updatedAt.toISOString(),
  };
}

export function serializeShipmentDetail(s: ShipmentDetailRow) {
  return {
    ...serializeShipment(s),
    packages: s.packages.map(serializePackage),
  };
}
