-- Migration: Add university_id column to tasks table
-- This allows tasks to be linked to specific locked universities

-- Add the column (nullable to allow existing tasks)
ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS university_id INTEGER NULL;

-- Add comment for documentation
COMMENT ON COLUMN tasks.university_id IS 'Links task to a specific university. NULL means generic pre-lock task.';

-- Optional: Add index for performance
CREATE INDEX IF NOT EXISTS idx_tasks_university_id ON tasks(university_id);

-- Verify the change
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'tasks'
ORDER BY ordinal_position;
