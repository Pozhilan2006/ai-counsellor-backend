-- ============================================
-- Tasks Table Migration: Add university_id
-- ============================================
-- Run this in Supabase SQL Editor
-- ============================================

-- Step 1: Add university_id column (nullable for existing rows)
ALTER TABLE tasks 
ADD COLUMN IF NOT EXISTS university_id INTEGER;

-- Step 2: Add foreign key constraint (with conditional check)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_tasks_university' 
        AND table_name = 'tasks'
    ) THEN
        ALTER TABLE tasks
        ADD CONSTRAINT fk_tasks_university
        FOREIGN KEY (university_id)
        REFERENCES universities(id)
        ON DELETE SET NULL;
    END IF;
END $$;

-- Step 3: Create composite index for efficient queries
CREATE INDEX IF NOT EXISTS idx_tasks_user_university
ON tasks(user_id, university_id);

-- Step 4: Create index on university_id alone for FK lookups
CREATE INDEX IF NOT EXISTS idx_tasks_university_id
ON tasks(university_id);

-- ============================================
-- Verification Query
-- ============================================
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'tasks'
ORDER BY ordinal_position;
