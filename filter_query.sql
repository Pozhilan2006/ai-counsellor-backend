-- SQL Query Example
-- ===================
-- Filter universities based on user constraints
-- Backend executes this BEFORE sending data to AI

-- Example: User wants USA/Canada, budget $30,000

SELECT 
    id,
    name,
    country,
    rank,
    ranking_band,
    competitiveness,
    avg_tuition_usd
FROM universities
WHERE 
    country IN ('United States', 'Canada')  -- User preferred countries
    AND avg_tuition_usd <= 36000  -- Budget * 1.2 (30000 * 1.2)
    AND ranking_band IN ('Top 50', '50-100', '100-300', '300+')  -- All bands
ORDER BY rank ASC
LIMIT 30;

-- PostgreSQL version with array parameter
-- ----------------------------------------
SELECT 
    id,
    name,
    country,
    rank,
    ranking_band,
    competitiveness,
    avg_tuition_usd
FROM universities
WHERE 
    country = ANY($1::text[])  -- Array of countries
    AND avg_tuition_usd <= $2  -- Max tuition
ORDER BY rank ASC
LIMIT 30;

-- Example parameters:
-- $1 = ['United States', 'Canada']
-- $2 = 36000
