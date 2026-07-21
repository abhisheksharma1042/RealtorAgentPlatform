-- Migration 007: Plutus memory layer.
-- pins / saved searches / skill profile all carry user_id so the MVP
-- Supabase Auth flip is a config change, not a migration.
-- data_coverage is a VIEW so coverage claims are always live DB truth.

BEGIN;

CREATE TABLE IF NOT EXISTS pinned_properties (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  note        TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, property_id)
);
CREATE INDEX IF NOT EXISTS idx_pinned_properties_user ON pinned_properties(user_id);

CREATE TABLE IF NOT EXISTS saved_searches (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  name        TEXT NOT NULL,
  criteria    JSONB NOT NULL,
  client_note TEXT,
  last_run_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON saved_searches(user_id);

CREATE TABLE IF NOT EXISTS skill_profile (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL,
  concept          TEXT NOT NULL,
  level            TEXT NOT NULL CHECK (level IN ('novice', 'learning', 'familiar')),
  evidence_count   INTEGER NOT NULL DEFAULT 1,
  notes            TEXT,
  last_observed_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (user_id, concept)
);
CREATE INDEX IF NOT EXISTS idx_skill_profile_user ON skill_profile(user_id);

CREATE TABLE IF NOT EXISTS zip_boundaries (
  zip        VARCHAR(10) PRIMARY KEY,
  boundary   JSONB NOT NULL,   -- GeoJSON Feature from Census TIGERweb ZCTA
  fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE VIEW data_coverage AS
SELECT
  cp.county,
  cp.situs_zip                              AS zip,
  COUNT(*)::int                             AS parcel_count,
  COUNT(cp.location)::int                   AS geocoded_count,
  MAX(cp.tax_year)                          AS appraisal_year,
  (SELECT COUNT(*)::int FROM properties p
     WHERE p.zip_code = cp.situs_zip AND p.sold_price IS NOT NULL)      AS sold_listing_count,
  (SELECT MIN(ms.period) FROM market_stats ms
     WHERE ms.zip_code = cp.situs_zip)                                  AS stats_from,
  (SELECT MAX(ms.period) FROM market_stats ms
     WHERE ms.zip_code = cp.situs_zip)                                  AS stats_to
FROM county_parcels cp
WHERE cp.situs_zip IS NOT NULL
GROUP BY cp.county, cp.situs_zip;

COMMIT;
