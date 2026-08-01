-- Initial Migration Schema for PostgreSQL - GatePro Platform

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'student',
    full_name VARCHAR(255),
    target_year INTEGER DEFAULT 2025,
    target_subject VARCHAR(255) DEFAULT 'Chemical Engineering',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- PYQ Question Papers Table
CREATE TABLE IF NOT EXISTS pyqs (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    subject VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    total_questions INTEGER NOT NULL DEFAULT 65,
    total_marks INTEGER NOT NULL DEFAULT 100,
    duration_minutes INTEGER NOT NULL DEFAULT 180,
    difficulty VARCHAR(50) DEFAULT 'GATE Official',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Questions Table
CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    pyq_id INTEGER REFERENCES pyqs(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    subject VARCHAR(255) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    question_text TEXT NOT NULL,
    question_type VARCHAR(50) NOT NULL DEFAULT 'MCQ',
    options_json JSONB,
    correct_answer TEXT NOT NULL,
    nat_range_min DOUBLE PRECISION,
    nat_range_max DOUBLE PRECISION,
    marks INTEGER NOT NULL DEFAULT 1,
    negative_marks DOUBLE PRECISION NOT NULL DEFAULT 0.33,
    difficulty VARCHAR(50) NOT NULL DEFAULT 'GATE Official',
    explanation TEXT,
    formulas_json JSONB
);

-- Test Results Table
CREATE TABLE IF NOT EXISTS test_results (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    paper_title VARCHAR(255) NOT NULL,
    paper_year INTEGER NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    max_score DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION NOT NULL,
    correct_count INTEGER NOT NULL,
    incorrect_count INTEGER NOT NULL,
    unattempted_count INTEGER NOT NULL,
    time_taken_seconds INTEGER NOT NULL,
    subject_breakdown_json JSONB,
    user_answers_json JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Leaderboard Table
CREATE TABLE IF NOT EXISTS leaderboard (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username VARCHAR(255) NOT NULL,
    total_tests INTEGER DEFAULT 0,
    highest_score DOUBLE PRECISION DEFAULT 0,
    avg_accuracy DOUBLE PRECISION DEFAULT 0,
    total_score DOUBLE PRECISION DEFAULT 0,
    air_estimate INTEGER DEFAULT 100,
    badge VARCHAR(100) DEFAULT 'Aspirant',
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- User Alarms Table
CREATE TABLE IF NOT EXISTS user_alarms (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    time_str VARCHAR(50) NOT NULL,
    label VARCHAR(255) NOT NULL,
    days_json JSONB DEFAULT '["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]'::jsonb,
    is_active INTEGER DEFAULT 1,
    sound_type VARCHAR(100) DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Study Sessions Table
CREATE TABLE IF NOT EXISTS study_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    duration_minutes INTEGER NOT NULL,
    topic VARCHAR(255) NOT NULL,
    notes TEXT,
    date_str VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Performance & Query Optimization Indexes
CREATE INDEX IF NOT EXISTS idx_questions_pyq_id ON questions (pyq_id);
CREATE INDEX IF NOT EXISTS idx_questions_question_number ON questions (question_number);
CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions (subject);
CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions (topic);

CREATE INDEX IF NOT EXISTS idx_pyqs_year ON pyqs (year);
CREATE INDEX IF NOT EXISTS idx_pyqs_subject ON pyqs (subject);

CREATE INDEX IF NOT EXISTS idx_test_results_user_id ON test_results (user_id);
CREATE INDEX IF NOT EXISTS idx_leaderboard_user_id ON leaderboard (user_id);
CREATE INDEX IF NOT EXISTS idx_user_alarms_user_id ON user_alarms (user_id);
CREATE INDEX IF NOT EXISTS idx_study_sessions_user_id ON study_sessions (user_id);
