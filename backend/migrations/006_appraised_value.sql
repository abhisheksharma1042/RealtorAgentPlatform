-- Migration 006: Surface DCAD's total_appraised as a first-class field on properties.
-- Texas is a non-disclosure state so we can't have sold_price for county-sourced
-- parcels, but appraisal value IS public and useful for realtors.

BEGIN;

ALTER TABLE properties ADD COLUMN IF NOT EXISTS appraised_value DECIMAL(12, 2);
CREATE INDEX IF NOT EXISTS idx_properties_appraised_value ON properties(appraised_value);

COMMIT;
