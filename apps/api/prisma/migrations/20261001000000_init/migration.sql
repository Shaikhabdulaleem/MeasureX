-- CreateEnum
CREATE TYPE "Role" AS ENUM ('labour', 'team_leader', 'admin');

-- CreateEnum
CREATE TYPE "BranchStatus" AS ENUM ('active', 'inactive');

-- CreateEnum
CREATE TYPE "DeviceTier" AS ENUM ('standard', 'ar', 'unsupported');

-- CreateEnum
CREATE TYPE "ScaleConnection" AS ENUM ('ble', 'classic', 'hid');

-- CreateEnum
CREATE TYPE "ShipmentStatus" AS ENUM ('in_progress', 'completed', 'remeasure_required');

-- CreateEnum
CREATE TYPE "PackageStatus" AS ENUM ('active', 'superseded', 'void');

-- CreateEnum
CREATE TYPE "WeightSource" AS ENUM ('scale', 'manual', 'none');

-- CreateEnum
CREATE TYPE "MeasurementMethod" AS ENUM ('marker', 'ar', 'manual');

-- CreateEnum
CREATE TYPE "Confidence" AS ENUM ('high', 'medium', 'low');

-- CreateEnum
CREATE TYPE "PhotoKind" AS ENUM ('raw', 'annotated');

-- CreateEnum
CREATE TYPE "RemeasureStatus" AS ENUM ('open', 'done', 'cancelled');

-- CreateEnum
CREATE TYPE "RemeasureReason" AS ENUM ('low_confidence', 'incorrect_dimensions', 'bad_photo', 'device_issue', 'customer_dispute', 'manual_verification', 'other');

-- CreateEnum
CREATE TYPE "FlagStatus" AS ENUM ('open', 'resolved', 'dismissed');

-- CreateEnum
CREATE TYPE "FlagType" AS ENUM ('low_confidence', 'medium_confidence', 'manual_entry', 'manual_weight', 'weight_discrepancy', 'check_dimensions', 'possible_duplicate', 'worker_flag');

-- CreateEnum
CREATE TYPE "ConfigScope" AS ENUM ('global', 'client', 'branch');

-- CreateEnum
CREATE TYPE "SyncStatus" AS ENUM ('pending', 'syncing', 'synced', 'failed', 'conflict');

-- CreateTable
CREATE TABLE "branch" (
    "id" UUID NOT NULL,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "status" "BranchStatus" NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "branch_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "client" (
    "id" UUID NOT NULL,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "aymakan_account_no" TEXT,
    "volumetric_divisor" INTEGER,
    "status" "BranchStatus" NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "client_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user" (
    "id" UUID NOT NULL,
    "employee_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "role" "Role" NOT NULL,
    "home_branch_id" UUID NOT NULL,
    "admin_scope" JSONB,
    "password_hash" TEXT NOT NULL,
    "must_change_password" BOOLEAN NOT NULL DEFAULT true,
    "failed_logins" INTEGER NOT NULL DEFAULT 0,
    "locked_until" TIMESTAMP(3),
    "status" "BranchStatus" NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "user_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "session" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "refresh_token_hash" TEXT NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "revoked_at" TIMESTAMP(3),
    "install_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "session_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "station" (
    "id" UUID NOT NULL,
    "code" TEXT NOT NULL,
    "branch_id" UUID NOT NULL,
    "mat_size_mm" INTEGER NOT NULL,
    "marker_size_mm" INTEGER NOT NULL,
    "scale_id" UUID,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "station_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scale" (
    "id" UUID NOT NULL,
    "model" TEXT NOT NULL,
    "connection" "ScaleConnection" NOT NULL,
    "adapter_key" TEXT NOT NULL,
    "approved" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "scale_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "device" (
    "id" UUID NOT NULL,
    "install_id" TEXT NOT NULL,
    "manufacturer" TEXT,
    "model" TEXT,
    "os" TEXT,
    "os_version" TEXT,
    "tier" "DeviceTier" NOT NULL,
    "last_user_id" UUID,
    "last_seen_at" TIMESTAMP(3),
    "blocked" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "device_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "shipment" (
    "id" UUID NOT NULL,
    "awb" TEXT NOT NULL,
    "branch_id" UUID,
    "client_id" UUID,
    "expected_pieces" INTEGER,
    "declared_weight_g" INTEGER,
    "origin" TEXT,
    "destination" TEXT,
    "client_ref" TEXT,
    "status" "ShipmentStatus" NOT NULL DEFAULT 'in_progress',
    "flags" "FlagType"[] DEFAULT ARRAY[]::"FlagType"[],
    "total_pieces" INTEGER NOT NULL DEFAULT 0,
    "total_cbm" DECIMAL(14,4) NOT NULL DEFAULT 0,
    "total_actual_g" INTEGER NOT NULL DEFAULT 0,
    "total_volumetric_g" INTEGER NOT NULL DEFAULT 0,
    "total_chargeable_g" INTEGER NOT NULL DEFAULT 0,
    "completed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "shipment_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "package" (
    "id" UUID NOT NULL,
    "shipment_id" UUID NOT NULL,
    "package_number" INTEGER,
    "provisional_number" INTEGER,
    "status" "PackageStatus" NOT NULL DEFAULT 'active',
    "current_version_id" UUID,
    "station_id" UUID,
    "device_id" UUID,
    "measured_by" UUID,
    "idempotency_key" TEXT,
    "confirmed_at" TIMESTAMP(3),
    "sync_received_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "package_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "measurement_version" (
    "id" UUID NOT NULL,
    "package_id" UUID NOT NULL,
    "version_no" INTEGER NOT NULL,
    "length_mm" INTEGER NOT NULL,
    "width_mm" INTEGER NOT NULL,
    "height_mm" INTEGER NOT NULL,
    "actual_weight_g" INTEGER,
    "weight_source" "WeightSource" NOT NULL DEFAULT 'none',
    "scale_id" UUID,
    "method" "MeasurementMethod" NOT NULL,
    "confidence" "Confidence",
    "confidence_detail" JSONB,
    "divisor_used" INTEGER NOT NULL,
    "billing_l_cm" INTEGER NOT NULL,
    "billing_w_cm" INTEGER NOT NULL,
    "billing_h_cm" INTEGER NOT NULL,
    "cbm" DECIMAL(14,4) NOT NULL,
    "volumetric_g" INTEGER NOT NULL,
    "chargeable_g" INTEGER NOT NULL,
    "created_by" UUID,
    "reason" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "measurement_version_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "photo" (
    "id" UUID NOT NULL,
    "package_id" UUID NOT NULL,
    "version_id" UUID,
    "kind" "PhotoKind" NOT NULL DEFAULT 'raw',
    "storage_key" TEXT NOT NULL,
    "width" INTEGER,
    "height" INTEGER,
    "bytes" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "photo_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "remeasure_request" (
    "id" UUID NOT NULL,
    "shipment_id" UUID NOT NULL,
    "package_ids" UUID[],
    "reason" "RemeasureReason" NOT NULL,
    "note" TEXT,
    "status" "RemeasureStatus" NOT NULL DEFAULT 'open',
    "requested_by" UUID NOT NULL,
    "done_by" UUID,
    "closed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "remeasure_request_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "flag" (
    "id" UUID NOT NULL,
    "shipment_id" UUID,
    "package_id" UUID,
    "type" "FlagType" NOT NULL,
    "status" "FlagStatus" NOT NULL DEFAULT 'open',
    "resolved_by" UUID,
    "note" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "flag_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "measurement_event" (
    "id" UUID NOT NULL,
    "device_id" UUID,
    "user_id" UUID,
    "awb" TEXT,
    "type" TEXT NOT NULL,
    "payload" JSONB,
    "occurred_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "measurement_event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_log" (
    "id" UUID NOT NULL,
    "at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" UUID,
    "role" "Role",
    "entity" TEXT NOT NULL,
    "entity_id" TEXT,
    "action" TEXT NOT NULL,
    "before" JSONB,
    "after" JSONB,
    "reason" TEXT,
    "ip" TEXT,
    "device_id" UUID,

    CONSTRAINT "audit_log_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "config" (
    "key" TEXT NOT NULL,
    "value" JSONB NOT NULL,
    "scope" "ConfigScope" NOT NULL DEFAULT 'global',
    "scope_id" TEXT,
    "updated_by" UUID,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "config_pkey" PRIMARY KEY ("key")
);

-- CreateIndex
CREATE UNIQUE INDEX "branch_code_key" ON "branch"("code");

-- CreateIndex
CREATE UNIQUE INDEX "client_code_key" ON "client"("code");

-- CreateIndex
CREATE UNIQUE INDEX "user_employee_id_key" ON "user"("employee_id");

-- CreateIndex
CREATE INDEX "user_home_branch_id_idx" ON "user"("home_branch_id");

-- CreateIndex
CREATE INDEX "session_user_id_idx" ON "session"("user_id");

-- CreateIndex
CREATE UNIQUE INDEX "station_code_key" ON "station"("code");

-- CreateIndex
CREATE INDEX "station_branch_id_idx" ON "station"("branch_id");

-- CreateIndex
CREATE UNIQUE INDEX "device_install_id_key" ON "device"("install_id");

-- CreateIndex
CREATE INDEX "device_last_user_id_idx" ON "device"("last_user_id");

-- CreateIndex
CREATE UNIQUE INDEX "shipment_awb_key" ON "shipment"("awb");

-- CreateIndex
CREATE INDEX "shipment_branch_id_idx" ON "shipment"("branch_id");

-- CreateIndex
CREATE INDEX "shipment_status_idx" ON "shipment"("status");

-- CreateIndex
CREATE UNIQUE INDEX "package_current_version_id_key" ON "package"("current_version_id");

-- CreateIndex
CREATE UNIQUE INDEX "package_idempotency_key_key" ON "package"("idempotency_key");

-- CreateIndex
CREATE INDEX "package_shipment_id_idx" ON "package"("shipment_id");

-- CreateIndex
CREATE INDEX "package_status_idx" ON "package"("status");

-- CreateIndex
CREATE UNIQUE INDEX "package_shipment_id_package_number_key" ON "package"("shipment_id", "package_number");

-- CreateIndex
CREATE INDEX "measurement_version_package_id_idx" ON "measurement_version"("package_id");

-- CreateIndex
CREATE UNIQUE INDEX "measurement_version_package_id_version_no_key" ON "measurement_version"("package_id", "version_no");

-- CreateIndex
CREATE INDEX "photo_package_id_idx" ON "photo"("package_id");

-- CreateIndex
CREATE INDEX "remeasure_request_shipment_id_idx" ON "remeasure_request"("shipment_id");

-- CreateIndex
CREATE INDEX "remeasure_request_status_idx" ON "remeasure_request"("status");

-- CreateIndex
CREATE INDEX "flag_shipment_id_idx" ON "flag"("shipment_id");

-- CreateIndex
CREATE INDEX "flag_package_id_idx" ON "flag"("package_id");

-- CreateIndex
CREATE INDEX "flag_status_idx" ON "flag"("status");

-- CreateIndex
CREATE INDEX "measurement_event_awb_idx" ON "measurement_event"("awb");

-- CreateIndex
CREATE INDEX "measurement_event_type_idx" ON "measurement_event"("type");

-- CreateIndex
CREATE INDEX "measurement_event_occurred_at_idx" ON "measurement_event"("occurred_at");

-- CreateIndex
CREATE INDEX "audit_log_entity_entity_id_idx" ON "audit_log"("entity", "entity_id");

-- CreateIndex
CREATE INDEX "audit_log_at_idx" ON "audit_log"("at");

-- AddForeignKey
ALTER TABLE "user" ADD CONSTRAINT "user_home_branch_id_fkey" FOREIGN KEY ("home_branch_id") REFERENCES "branch"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "session" ADD CONSTRAINT "session_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "station" ADD CONSTRAINT "station_branch_id_fkey" FOREIGN KEY ("branch_id") REFERENCES "branch"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "station" ADD CONSTRAINT "station_scale_id_fkey" FOREIGN KEY ("scale_id") REFERENCES "scale"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "device" ADD CONSTRAINT "device_last_user_id_fkey" FOREIGN KEY ("last_user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "shipment" ADD CONSTRAINT "shipment_branch_id_fkey" FOREIGN KEY ("branch_id") REFERENCES "branch"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "shipment" ADD CONSTRAINT "shipment_client_id_fkey" FOREIGN KEY ("client_id") REFERENCES "client"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "package" ADD CONSTRAINT "package_shipment_id_fkey" FOREIGN KEY ("shipment_id") REFERENCES "shipment"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "package" ADD CONSTRAINT "package_station_id_fkey" FOREIGN KEY ("station_id") REFERENCES "station"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "package" ADD CONSTRAINT "package_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "device"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "package" ADD CONSTRAINT "package_measured_by_fkey" FOREIGN KEY ("measured_by") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "package" ADD CONSTRAINT "package_current_version_id_fkey" FOREIGN KEY ("current_version_id") REFERENCES "measurement_version"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "measurement_version" ADD CONSTRAINT "measurement_version_package_id_fkey" FOREIGN KEY ("package_id") REFERENCES "package"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "measurement_version" ADD CONSTRAINT "measurement_version_scale_id_fkey" FOREIGN KEY ("scale_id") REFERENCES "scale"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "measurement_version" ADD CONSTRAINT "measurement_version_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "photo" ADD CONSTRAINT "photo_package_id_fkey" FOREIGN KEY ("package_id") REFERENCES "package"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "photo" ADD CONSTRAINT "photo_version_id_fkey" FOREIGN KEY ("version_id") REFERENCES "measurement_version"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "remeasure_request" ADD CONSTRAINT "remeasure_request_shipment_id_fkey" FOREIGN KEY ("shipment_id") REFERENCES "shipment"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "remeasure_request" ADD CONSTRAINT "remeasure_request_requested_by_fkey" FOREIGN KEY ("requested_by") REFERENCES "user"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "remeasure_request" ADD CONSTRAINT "remeasure_request_done_by_fkey" FOREIGN KEY ("done_by") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "flag" ADD CONSTRAINT "flag_shipment_id_fkey" FOREIGN KEY ("shipment_id") REFERENCES "shipment"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "flag" ADD CONSTRAINT "flag_package_id_fkey" FOREIGN KEY ("package_id") REFERENCES "package"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "flag" ADD CONSTRAINT "flag_resolved_by_fkey" FOREIGN KEY ("resolved_by") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "measurement_event" ADD CONSTRAINT "measurement_event_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "device"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "measurement_event" ADD CONSTRAINT "measurement_event_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_log" ADD CONSTRAINT "audit_log_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_log" ADD CONSTRAINT "audit_log_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "device"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "config" ADD CONSTRAINT "config_updated_by_fkey" FOREIGN KEY ("updated_by") REFERENCES "user"("id") ON DELETE SET NULL ON UPDATE CASCADE;

