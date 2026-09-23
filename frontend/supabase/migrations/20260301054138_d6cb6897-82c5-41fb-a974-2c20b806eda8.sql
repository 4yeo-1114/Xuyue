
-- Recreate match functions with extensions in search_path
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
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions
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
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, extensions
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
