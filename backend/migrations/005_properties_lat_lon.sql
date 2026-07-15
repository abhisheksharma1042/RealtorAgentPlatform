-- Migration 005: Add plain numeric lat/lon to properties.
-- Rationale: Supabase REST returns the location GEOGRAPHY column as
-- hex-encoded EWKB (e.g. '0101000020E610...') which the frontend can't
-- parse. Numeric columns come back as plain numbers.
-- The GEOGRAPHY column is retained for spatial queries.

BEGIN;

ALTER TABLE properties ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;

UPDATE properties
SET lat = ST_Y(location::geometry),
    lon = ST_X(location::geometry)
WHERE location IS NOT NULL AND lat IS NULL;

CREATE INDEX IF NOT EXISTS idx_properties_lat_lon ON properties(lat, lon);

COMMIT;
