-- Migration 004: Real DCAD BLDG_CLASS_DESC values can exceed 20 chars
-- (e.g. "SPECIAL (DESCRIBE IN COMMENTS)" = 30 chars). Widen to accommodate.

BEGIN;

ALTER TABLE county_parcels
  ALTER COLUMN land_use_code TYPE VARCHAR(50);

COMMIT;
