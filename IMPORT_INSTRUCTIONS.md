# Import universities_canonical.csv to PostgreSQL

## Option A: Using COPY Command (psql)

### Step 1: Create the table
```sql
CREATE TABLE universities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    rank INTEGER NOT NULL,
    ranking_band TEXT NOT NULL,
    competitiveness TEXT NOT NULL,
    avg_tuition_usd INTEGER NOT NULL
);
```

### Step 2: Import CSV using \COPY
```bash
psql -h your-host -U your-user -d your-database -c "\COPY universities(name, country, rank, ranking_band, competitiveness, avg_tuition_usd) FROM 'universities_canonical.csv' WITH (FORMAT csv, HEADER true);"
```

Or from within psql:
```sql
\COPY universities(name, country, rank, ranking_band, competitiveness, avg_tuition_usd) FROM '/absolute/path/to/universities_canonical.csv' WITH (FORMAT csv, HEADER true);
```

### Step 3: Verify
```sql
SELECT COUNT(*) FROM universities;
SELECT * FROM universities LIMIT 10;
```

---

## Option B: Using Supabase Dashboard

### Step 1: Create the table
1. Go to Supabase Dashboard → SQL Editor
2. Run:
```sql
CREATE TABLE universities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    rank INTEGER NOT NULL,
    ranking_band TEXT NOT NULL,
    competitiveness TEXT NOT NULL,
    avg_tuition_usd INTEGER NOT NULL
);
```

### Step 2: Import CSV
1. Go to Table Editor → `universities` table
2. Click "Insert" → "Import data from CSV"
3. Upload `universities_canonical.csv`
4. Map columns:
   - name → name
   - country → country
   - rank → rank
   - ranking_band → ranking_band
   - competitiveness → competitiveness
   - avg_tuition_usd → avg_tuition_usd
5. Skip `id` column (auto-generated)
6. Click "Import"

### Step 3: Verify
```sql
SELECT COUNT(*) FROM universities;
SELECT * FROM universities LIMIT 10;
```

---

## Verification Queries

```sql
-- Total count
SELECT COUNT(*) FROM universities;

-- Sample data
SELECT * FROM universities LIMIT 10;

-- By country
SELECT country, COUNT(*) as count 
FROM universities 
GROUP BY country 
ORDER BY count DESC;

-- By ranking band
SELECT ranking_band, COUNT(*) as count 
FROM universities 
GROUP BY ranking_band 
ORDER BY ranking_band;

-- By competitiveness
SELECT competitiveness, COUNT(*) as count 
FROM universities 
GROUP BY competitiveness;
```
