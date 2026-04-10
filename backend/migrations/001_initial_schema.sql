-- DFW Realtor Agent Platform - Initial Database Schema
-- Run this in your Supabase SQL Editor

-- Enable PostGIS extension for geospatial queries
CREATE EXTENSION IF NOT EXISTS postgis;

-- Properties table with PostGIS location
CREATE TABLE IF NOT EXISTS properties (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mls_id VARCHAR(50) UNIQUE NOT NULL,
  address TEXT NOT NULL,
  city VARCHAR(100) NOT NULL,
  zip_code VARCHAR(10) NOT NULL,
  location GEOGRAPHY(POINT, 4326),  -- PostGIS point (lon, lat)
  price DECIMAL(12, 2),
  beds INTEGER,
  baths DECIMAL(3, 1),
  sqft INTEGER,
  lot_size_acres DECIMAL(8, 3),
  year_built INTEGER,
  property_type VARCHAR(50), -- single_family, condo, townhome
  status VARCHAR(20),  -- active, pending, sold
  list_date DATE,
  sold_date DATE,
  sold_price DECIMAL(12, 2),
  days_on_market INTEGER,
  price_per_sqft DECIMAL(8, 2),
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Market statistics (precomputed aggregates)
CREATE TABLE IF NOT EXISTS market_stats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zip_code VARCHAR(10) NOT NULL,
  period DATE NOT NULL,  -- First day of month
  property_type VARCHAR(50),
  median_price DECIMAL(12, 2),
  avg_price DECIMAL(12, 2),
  sales_volume INTEGER,
  avg_days_on_market DECIMAL(6, 1),
  median_list_to_sale_ratio DECIMAL(6, 4),
  median_price_per_sqft DECIMAL(8, 2),
  active_listings_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(zip_code, period, property_type)
);

-- Chat sessions for multi-user support
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID, -- Will link to auth.users in Phase 7
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat messages for session persistence
CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL,  -- user, assistant, tool
  content JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_properties_zip ON properties(zip_code);
CREATE INDEX IF NOT EXISTS idx_properties_status ON properties(status);
CREATE INDEX IF NOT EXISTS idx_properties_location ON properties USING GIST(location);
CREATE INDEX IF NOT EXISTS idx_properties_price ON properties(price);
CREATE INDEX IF NOT EXISTS idx_properties_beds ON properties(beds);
CREATE INDEX IF NOT EXISTS idx_properties_sold_date ON properties(sold_date);

CREATE INDEX IF NOT EXISTS idx_market_stats_zip_period ON market_stats(zip_code, period);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);

-- Comments for documentation
COMMENT ON TABLE properties IS 'Real estate properties in the DFW metroplex';
COMMENT ON TABLE market_stats IS 'Precomputed market statistics by ZIP code and time period';
COMMENT ON TABLE chat_sessions IS 'User chat sessions with the AI agent';
COMMENT ON TABLE chat_messages IS 'Individual messages within chat sessions';
