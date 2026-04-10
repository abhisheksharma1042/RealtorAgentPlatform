# Database Migrations

## Setup Instructions

### Step 1: Create Schema

1. Go to your Supabase dashboard: https://supabase.com/dashboard
2. Select your project: `cchkagosciauviahicwt`
3. Navigate to **SQL Editor** in the left sidebar
4. Click **New Query**
5. Copy and paste the contents of `001_initial_schema.sql`
6. Click **Run** or press `Ctrl/Cmd + Enter`

This will create:
- ✅ PostGIS extension
- ✅ `properties` table with geospatial support
- ✅ `market_stats` table for precomputed statistics
- ✅ `chat_sessions` and `chat_messages` tables
- ✅ All necessary indexes

### Step 2: Seed Sample Data

After the schema is created, run the Python seeding script:

```bash
cd backend
source venv/bin/activate
python migrations/002_seed_sample_data.py
```

This will generate:
- **180 properties** across 6 DFW ZIP codes
- **72 market statistics** records (12 months per ZIP)
- Realistic prices, features, and dates

### Available Sample Data

**ZIP Codes:**
- 75201 - Downtown Dallas (condos/townhomes, $250K-$600K)
- 75205 - Highland Park (single family, $800K-$2.5M)
- 75219 - Uptown Dallas (condos/townhomes, $300K-$800K)
- 75024 - Plano (single family, $350K-$650K)
- 75025 - West Plano (single family, $400K-$850K)
- 75034 - Frisco (single family, $400K-$750K)

### Verification

Test the database connection:

```bash
cd backend
source venv/bin/activate
python -c "from db.client import db; print('✅ Connected!' if db.test_connection() else '❌ Failed')"
```

## Troubleshooting

**Error: "extension postgis does not exist"**
- Go to Database → Extensions in Supabase dashboard
- Enable PostGIS extension manually

**Error: "relation does not exist"**
- Make sure Step 1 (schema creation) completed successfully
- Check for error messages in Supabase SQL Editor

**Error: "authentication failed"**
- Verify your `SUPABASE_SERVICE_KEY` in `backend/.env`
- Make sure you're using the service role key, not the anon key
