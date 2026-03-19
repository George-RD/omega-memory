-- OMEGA Cloud Schema -- Supabase PostgreSQL + pgvector
-- Run this in Supabase SQL Editor after creating the project.
--
-- Prerequisites:
--   1. Supabase project created (Pro tier recommended)
--   2. pgvector extension enabled

-- ============================================================================
-- Extensions
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Memories (synced replica from local OMEGA SQLite)
-- ============================================================================

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    local_id INTEGER,                 -- maps to local SQLite rowid
    content TEXT NOT NULL,
    event_type TEXT,                   -- decision, lesson_learned, etc.
    priority INTEGER DEFAULT 3,
    session_id TEXT,
    project TEXT,
    tags TEXT[],
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    synced_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_event_type ON memories(event_type);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_local_id ON memories(local_id);

-- ============================================================================
-- Memory Embeddings (pgvector -- 384-dim bge-small-en-v1.5)
-- ============================================================================

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    embedding vector(384)
);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_memory_id ON memory_embeddings(memory_id);

-- IVFFlat index for approximate nearest neighbor search
-- lists = ceil(sqrt(estimated_rows)); start with 50, increase as data grows
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_vector
    ON memory_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- ============================================================================
-- Documents (PDFs, websites, GDrive files)
-- ============================================================================

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    local_id INTEGER,                 -- maps to local SQLite rowid
    source_path TEXT NOT NULL,
    source_type TEXT NOT NULL,         -- 'pdf' | 'webpage' | 'markdown' | 'text' | 'gdrive'
    title TEXT,
    checksum TEXT,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    synced_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source_path)
);

CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);

-- ============================================================================
-- Document Chunks with inline vectors
-- ============================================================================

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    local_id INTEGER,                 -- maps to local SQLite rowid
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    chunk_type TEXT,                   -- 'section' | 'paragraph' | 'sentence_group'
    page_number INTEGER,
    token_count INTEGER,
    embedding vector(384),            -- inline embedding (pgvector)
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);

-- IVFFlat index for document chunk search
CREATE INDEX IF NOT EXISTS idx_document_chunks_vector
    ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- Encrypted Personal Profile (ciphertext only -- decryption is local)
-- ============================================================================

CREATE TABLE IF NOT EXISTS secure_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    local_id INTEGER,
    category TEXT NOT NULL,            -- 'identity' | 'medical' | 'financial' | etc.
    field_name TEXT NOT NULL,
    field_value_encrypted TEXT NOT NULL, -- AES-256 Fernet ciphertext
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    synced_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(category, field_name)
);

CREATE INDEX IF NOT EXISTS idx_secure_profile_category ON secure_profile(category);

-- ============================================================================
-- Sync metadata (tracks sync state between local and cloud)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name TEXT NOT NULL UNIQUE,
    last_sync_at TIMESTAMPTZ DEFAULT now(),
    last_local_id INTEGER DEFAULT 0,
    sync_count INTEGER DEFAULT 0
);

INSERT INTO sync_state (table_name) VALUES ('memories'), ('documents'), ('document_chunks'), ('secure_profile')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Row Level Security (RLS)
-- ============================================================================

ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE secure_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_state ENABLE ROW LEVEL SECURITY;

-- Policy: only authenticated user can access all their data
-- For single-user setup: auth.uid() check ensures no anonymous access
CREATE POLICY "Users can manage their own memories"
    ON memories FOR ALL
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "Users can manage their own memory embeddings"
    ON memory_embeddings FOR ALL
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "Users can manage their own documents"
    ON documents FOR ALL
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "Users can manage their own document chunks"
    ON document_chunks FOR ALL
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "Users can manage their own profile"
    ON secure_profile FOR ALL
    USING (auth.uid() IS NOT NULL);

CREATE POLICY "Users can manage sync state"
    ON sync_state FOR ALL
    USING (auth.uid() IS NOT NULL);

-- ============================================================================
-- Helper functions
-- ============================================================================

-- Semantic search function for memories
CREATE OR REPLACE FUNCTION search_memories(
    query_embedding vector(384),
    match_count INT DEFAULT 10,
    match_threshold FLOAT DEFAULT 0.3
)
RETURNS TABLE (
    memory_id UUID,
    content TEXT,
    event_type TEXT,
    priority INTEGER,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id AS memory_id,
        m.content,
        m.event_type,
        m.priority,
        1 - (me.embedding <=> query_embedding) AS similarity
    FROM memory_embeddings me
    JOIN memories m ON m.id = me.memory_id
    WHERE 1 - (me.embedding <=> query_embedding) > match_threshold
    ORDER BY me.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Semantic search function for document chunks
CREATE OR REPLACE FUNCTION search_documents(
    query_embedding vector(384),
    match_count INT DEFAULT 5,
    match_threshold FLOAT DEFAULT 0.3,
    filter_source_type TEXT DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    document_title TEXT,
    source_path TEXT,
    source_type TEXT,
    content TEXT,
    chunk_type TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id AS chunk_id,
        d.title AS document_title,
        d.source_path,
        d.source_type,
        dc.content,
        dc.chunk_type,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id
    WHERE 1 - (dc.embedding <=> query_embedding) > match_threshold
      AND (filter_source_type IS NULL OR d.source_type = filter_source_type)
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
