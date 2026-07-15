-- Migration 003: Ingestion pipeline (raw layer + properties alterations)

BEGIN;

CREATE TABLE IF NOT EXISTS county_parcels (
  county            VARCHAR(20)  NOT NULL,
  account_num       VARCHAR(40)  NOT NULL,
  situs_address     TEXT         NOT NULL,
  situs_zip         VARCHAR(10),
  city              VARCHAR(100),
  land_use_code     VARCHAR(20),
  living_area_sqft  INTEGER,
  land_sqft         INTEGER,
  year_built        INTEGER,
  bedrooms          INTEGER,
  bathrooms         DECIMAL(3,1),
  total_appraised   DECIMAL(12,2),
  land_value        DECIMAL(12,2),
  improvement_value DECIMAL(12,2),
  tax_year          INTEGER,
  location          GEOGRAPHY(POINT, 4326),
  raw               JSONB,
  source_updated_at TIMESTAMPTZ,
  fetched_at        TIMESTAMPTZ  DEFAULT NOW(),
  PRIMARY KEY (county, account_num)
);
CREATE INDEX IF NOT EXISTS idx_county_parcels_zip     ON county_parcels(situs_zip);
CREATE INDEX IF NOT EXISTS idx_county_parcels_address ON county_parcels
  USING GIN(to_tsvector('english', situs_address));
CREATE INDEX IF NOT EXISTS idx_county_parcels_loc     ON county_parcels USING GIST(location);

CREATE TABLE IF NOT EXISTS api_responses (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider     VARCHAR(30)  NOT NULL,
  endpoint     VARCHAR(50)  NOT NULL,
  cache_key    TEXT         NOT NULL,
  params       JSONB        NOT NULL,
  response     JSONB        NOT NULL,
  fetched_at   TIMESTAMPTZ  DEFAULT NOW(),
  expires_at   TIMESTAMPTZ,
  UNIQUE(provider, endpoint, cache_key)
);
CREATE INDEX IF NOT EXISTS idx_api_responses_provider_endpoint ON api_responses(provider, endpoint);
CREATE INDEX IF NOT EXISTS idx_api_responses_expires           ON api_responses(expires_at);

CREATE TABLE IF NOT EXISTS api_budget (
  provider       VARCHAR(30)  NOT NULL,
  period         DATE         NOT NULL,
  requests_used  INTEGER      NOT NULL DEFAULT 0,
  monthly_limit  INTEGER      NOT NULL,
  updated_at     TIMESTAMPTZ  DEFAULT NOW(),
  PRIMARY KEY (provider, period)
);

CREATE TABLE IF NOT EXISTS enrichment_cache (
  source     VARCHAR(30)  NOT NULL,
  cache_key  TEXT         NOT NULL,
  data       JSONB        NOT NULL,
  fetched_at TIMESTAMPTZ  DEFAULT NOW(),
  expires_at TIMESTAMPTZ,
  PRIMARY KEY (source, cache_key)
);

ALTER TABLE properties ALTER COLUMN mls_id DROP NOT NULL;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS external_id       VARCHAR(64);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS source            VARCHAR(30);
ALTER TABLE properties ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS last_synced_at    TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_source_external ON properties(source, external_id);

COMMIT;
