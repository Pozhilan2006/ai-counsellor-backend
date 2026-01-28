-- Step 1: Create the universities table
CREATE TABLE universities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    rank INTEGER NOT NULL,
    ranking_band TEXT NOT NULL,
    competitiveness TEXT NOT NULL,
    avg_tuition_usd INTEGER NOT NULL
);

-- Step 2a: Import using COPY command (PostgreSQL CLI or psql)
-- Run this from psql or PostgreSQL client:
\COPY universities(name, country, rank, ranking_band, competitiveness, avg_tuition_usd) FROM '/absolute/path/to/universities_canonical.csv' WITH (FORMAT csv, HEADER true);

-- Alternative for server-side COPY (requires superuser):
-- COPY universities(name, country, rank, ranking_band, competitiveness, avg_tuition_usd) FROM '/absolute/path/to/universities_canonical.csv' WITH (FORMAT csv, HEADER true);

-- Step 3: Verification queries
-- Count total rows
SELECT COUNT(*) FROM universities;

-- View first 10 rows
SELECT * FROM universities LIMIT 10;

-- Check data by country
SELECT country, COUNT(*) as count FROM universities GROUP BY country ORDER BY count DESC;

-- Check ranking bands distribution
SELECT ranking_band, COUNT(*) as count FROM universities GROUP BY ranking_band ORDER BY ranking_band;
