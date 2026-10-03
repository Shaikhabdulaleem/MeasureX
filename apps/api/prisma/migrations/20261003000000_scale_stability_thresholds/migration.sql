-- M2 (Scale): per-model stability thresholds on the approved-scale record
-- (PRD §9). Defaults match the PRD "stable weight rule" so existing rows keep
-- working; Admin may tune them per model.
ALTER TABLE "scale"
    ADD COLUMN "stability_window" INTEGER NOT NULL DEFAULT 5,
    ADD COLUMN "stability_tolerance_g" INTEGER NOT NULL DEFAULT 20,
    ADD COLUMN "stability_window_ms" INTEGER NOT NULL DEFAULT 1500,
    ADD COLUMN "min_weight_g" INTEGER NOT NULL DEFAULT 50,
    ADD COLUMN "stale_after_ms" INTEGER NOT NULL DEFAULT 5000;
