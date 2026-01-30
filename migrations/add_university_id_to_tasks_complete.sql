-- ============================================
-- Tasks Table Migration: Add university_id
-- ============================================
-- This migration adds university_id column to tasks table
-- with proper foreign key constraint and indexes.
--
-- Run this in Supabase SQL Editor or via psql
-- ============================================

-- Step 1: Add university_id column (nullable for existing rows)
ALTER TABLE tasks 
ADD COLUMN IF NOT EXISTS university_id INTEGER;

-- Step 2: Add foreign key constraint to universities table
-- ON DELETE SET NULL ensures tasks aren't deleted if university is removed
ALTER TABLE tasks
ADD CONSTRAINT IF NOT EXISTS fk_tasks_university
FOREIGN KEY (university_id)
REFERENCES universities(id)
ON DELETE SET NULL;

-- Step 3: Create composite index for efficient queries
-- This speeds up queries filtering by user_id + university_id
CREATE INDEX IF NOT EXISTS idx_tasks_user_university
ON tasks(user_id, university_id);

-- Step 4: Create index on university_id alone for FK lookups
CREATE INDEX IF NOT EXISTS idx_tasks_university_id
ON tasks(university_id);

-- ============================================
-- Verification Query
-- ============================================
-- Run this to verify the migration succeeded:

SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'tasks'
ORDER BY ordinal_position;

-- Expected output should include:
-- university_id | integer | YES | NULL

-- ============================================
-- Verify Foreign Key
-- ============================================
SELECT
    tc.constraint_name,
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.table_name = 'tasks' 
    AND tc.constraint_type = 'FOREIGN KEY';

-- Expected output should include:
-- fk_tasks_university | tasks | university_id | universities | id

-- ============================================
-- Verify Indexes
-- ============================================
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'tasks'
ORDER BY indexname;

-- Expected output should include:
-- idx_tasks_user_university
-- idx_tasks_university_id
