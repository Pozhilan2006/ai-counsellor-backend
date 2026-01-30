-- Migration: Create shortlists table
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS shortlists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    university_id INTEGER NOT NULL,
    category TEXT,
    locked BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_shortlists_user_id ON shortlists(user_id);
CREATE INDEX IF NOT EXISTS idx_shortlists_locked ON shortlists(user_id, locked) WHERE locked = true;

-- Ensure unique university per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_shortlists_user_university ON shortlists(user_id, university_id);
