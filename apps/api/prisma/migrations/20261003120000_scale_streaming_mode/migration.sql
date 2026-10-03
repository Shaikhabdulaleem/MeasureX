-- M2 review: streaming vs one-shot capture mode per scale model (PRD §9).
-- Streaming scales use the 5-reading / 1.5 s rule and the stale timeout; one-shot
-- scales (HID keyboard, settle-then-send) keep a value until the next reading,
-- a drop below minWeightG, or disconnect. Defaulted by connection on create.
ALTER TABLE "scale" ADD COLUMN "streaming" BOOLEAN NOT NULL DEFAULT true;
