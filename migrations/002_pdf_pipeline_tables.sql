-- Migration 002: PDF Pipeline Tables (papers, questions, options, question_images)

-- Papers Table
CREATE TABLE IF NOT EXISTS papers (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    subject VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    pdf_path TEXT NOT NULL,
    file_hash VARCHAR(64) UNIQUE NOT NULL,
    total_questions INTEGER NOT NULL DEFAULT 0,
    total_marks INTEGER NOT NULL DEFAULT 0,
    duration_minutes INTEGER NOT NULL DEFAULT 180,
    difficulty VARCHAR(50) DEFAULT 'GATE Official',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Questions Table (Enhanced with paper_id reference)
-- If questions table already exists, add paper_id column if not present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='questions' AND column_name='paper_id'
    ) THEN
        ALTER TABLE questions ADD COLUMN paper_id INTEGER REFERENCES papers(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Options Table
CREATE TABLE IF NOT EXISTS options (
    id SERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_key VARCHAR(10) NOT NULL,
    option_text TEXT NOT NULL,
    is_correct BOOLEAN DEFAULT FALSE
);

-- Question Images Table
CREATE TABLE IF NOT EXISTS question_images (
    id SERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    caption TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast query lookup
CREATE INDEX IF NOT EXISTS idx_papers_file_hash ON papers (file_hash);
CREATE INDEX IF NOT EXISTS idx_papers_year_subject ON papers (year, subject);
CREATE INDEX IF NOT EXISTS idx_questions_paper_id ON questions (paper_id);
CREATE INDEX IF NOT EXISTS idx_options_question_id ON options (question_id);
CREATE INDEX IF NOT EXISTS idx_question_images_question_id ON question_images (question_id);
