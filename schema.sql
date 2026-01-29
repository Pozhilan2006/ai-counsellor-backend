-- State-Driven Backend Database Schema
-- Run this to create all required tables

-- User Profiles
CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255) UNIQUE NOT NULL,
    education_level VARCHAR(100),
    degree VARCHAR(255),
    graduation_year INTEGER,
    gpa DECIMAL(3,2),
    intended_degree VARCHAR(255),
    field_of_study VARCHAR(255),
    intake_year INTEGER,
    preferred_countries TEXT[],
    budget_per_year INTEGER,
    funding_plan VARCHAR(255),
    ielts_status VARCHAR(50),
    gre_gmat_status VARCHAR(50),
    sop_status VARCHAR(50),
    profile_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- User States
CREATE TABLE IF NOT EXISTS user_states (
    user_id INTEGER PRIMARY KEY REFERENCES user_profiles(id),
    current_stage VARCHAR(50) DEFAULT 'ONBOARDING',
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User Universities (Shortlist & Locked)
CREATE TABLE IF NOT EXISTS user_universities (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES user_profiles(id),
    university_id INTEGER NOT NULL,
    category VARCHAR(20),
    shortlisted BOOLEAN DEFAULT FALSE,
    locked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, university_id)
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES user_profiles(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    stage VARCHAR(50),
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_states_user_id ON user_states(user_id);
CREATE INDEX IF NOT EXISTS idx_user_universities_user_id ON user_universities(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_stage ON tasks(stage);
