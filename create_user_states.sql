-- Migration: Create user_states table
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS user_states (
    user_id INTEGER PRIMARY KEY REFERENCES user_profiles(id) ON DELETE CASCADE,
    current_stage TEXT NOT NULL DEFAULT 'ONBOARDING',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_states_user_id ON user_states(user_id);

-- Add trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_user_states_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_states_updated_at
    BEFORE UPDATE ON user_states
    FOR EACH ROW
    EXECUTE FUNCTION update_user_states_updated_at();
