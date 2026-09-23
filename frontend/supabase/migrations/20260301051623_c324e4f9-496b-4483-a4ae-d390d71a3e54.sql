
-- Create questions table for exam question bank
CREATE TABLE public.questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  subject TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT '选择题',
  content TEXT NOT NULL,
  answer TEXT,
  analysis TEXT,
  difficulty NUMERIC NOT NULL DEFAULT 0.5,
  score INTEGER NOT NULL DEFAULT 2,
  knowledge_points TEXT[] NOT NULL DEFAULT '{}',
  use_count INTEGER NOT NULL DEFAULT 0,
  tags TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.questions ENABLE ROW LEVEL SECURITY;

-- RLS policies
CREATE POLICY "Users can view their own questions"
  ON public.questions FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can create their own questions"
  ON public.questions FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own questions"
  ON public.questions FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own questions"
  ON public.questions FOR DELETE
  USING (auth.uid() = user_id);

-- Indexes for common queries
CREATE INDEX idx_questions_user_subject ON public.questions(user_id, subject);
CREATE INDEX idx_questions_knowledge_points ON public.questions USING GIN(knowledge_points);
CREATE INDEX idx_questions_tags ON public.questions USING GIN(tags);

-- Trigger for updated_at
CREATE TRIGGER update_questions_updated_at
  BEFORE UPDATE ON public.questions
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();
