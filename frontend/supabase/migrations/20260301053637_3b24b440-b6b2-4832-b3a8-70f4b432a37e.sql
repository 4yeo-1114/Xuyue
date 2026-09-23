
-- Drop old indexes and recreate with smaller dimension
DROP INDEX IF EXISTS questions_embedding_idx;
DROP INDEX IF EXISTS knowledge_points_embedding_idx;

-- Drop old vector columns and recreate with 128 dimensions (faster, lighter)
ALTER TABLE questions DROP COLUMN IF EXISTS embedding;
ALTER TABLE questions ADD COLUMN embedding vector(128);

ALTER TABLE knowledge_points DROP COLUMN IF EXISTS embedding;
ALTER TABLE knowledge_points ADD COLUMN embedding vector(128);

-- Recreate indexes with HNSW (faster than ivfflat for small datasets)
CREATE INDEX questions_embedding_idx ON questions USING hnsw (embedding vector_cosine_ops);
CREATE INDEX knowledge_points_embedding_idx ON knowledge_points USING hnsw (embedding vector_cosine_ops);

-- Update match functions for 128 dimensions
CREATE OR REPLACE FUNCTION match_questions(
  query_embedding vector(128),
  match_threshold float DEFAULT 0.3,
  match_count int DEFAULT 10,
  filter_user_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  content text,
  subject text,
  type text,
  difficulty numeric,
  score integer,
  use_count integer,
  knowledge_points text[],
  tags text[],
  similarity float
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT
    q.id, q.content, q.subject, q.type, q.difficulty, q.score, q.use_count,
    q.knowledge_points, q.tags,
    (1 - (q.embedding <=> query_embedding))::float AS similarity
  FROM public.questions q
  WHERE q.embedding IS NOT NULL
    AND (filter_user_id IS NULL OR q.user_id = filter_user_id)
    AND 1 - (q.embedding <=> query_embedding) > match_threshold
  ORDER BY q.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION match_knowledge_points(
  query_embedding vector(128),
  match_threshold float DEFAULT 0.3,
  match_count int DEFAULT 10,
  filter_user_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  name text,
  code text,
  mastery integer,
  is_weak boolean,
  difficulty text,
  level text,
  common_errors text,
  similarity float
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT
    kp.id, kp.name, kp.code, kp.mastery, kp.is_weak, kp.difficulty, kp.level,
    kp.common_errors,
    (1 - (kp.embedding <=> query_embedding))::float AS similarity
  FROM public.knowledge_points kp
  WHERE kp.embedding IS NOT NULL
    AND (filter_user_id IS NULL OR kp.user_id = filter_user_id)
    AND 1 - (kp.embedding <=> query_embedding) > match_threshold
  ORDER BY kp.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
