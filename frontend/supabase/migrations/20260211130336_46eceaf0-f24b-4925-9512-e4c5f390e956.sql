
-- Units table
CREATE TABLE public.subject_units (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  subject TEXT NOT NULL,
  semester TEXT NOT NULL,
  unit_index INTEGER NOT NULL,
  name TEXT NOT NULL,
  subtitle TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, subject, semester, unit_index)
);

ALTER TABLE public.subject_units ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own units" ON public.subject_units FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create their own units" ON public.subject_units FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own units" ON public.subject_units FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own units" ON public.subject_units FOR DELETE USING (auth.uid() = user_id);

CREATE TRIGGER update_subject_units_updated_at BEFORE UPDATE ON public.subject_units FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- Knowledge points table
CREATE TABLE public.knowledge_points (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  unit_id UUID NOT NULL REFERENCES public.subject_units(id) ON DELETE CASCADE,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  level TEXT NOT NULL DEFAULT '识记',
  mastery INTEGER NOT NULL DEFAULT 0,
  is_weak BOOLEAN NOT NULL DEFAULT false,
  prerequisite TEXT[] NOT NULL DEFAULT '{}',
  postrequisite TEXT[] NOT NULL DEFAULT '{}',
  related TEXT[] NOT NULL DEFAULT '{}',
  hours INTEGER NOT NULL DEFAULT 1,
  key_point TEXT NOT NULL DEFAULT '',
  difficulty TEXT NOT NULL DEFAULT '',
  common_errors TEXT NOT NULL DEFAULT '',
  resources JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, unit_id, code)
);

ALTER TABLE public.knowledge_points ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own knowledge_points" ON public.knowledge_points FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create their own knowledge_points" ON public.knowledge_points FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own knowledge_points" ON public.knowledge_points FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own knowledge_points" ON public.knowledge_points FOR DELETE USING (auth.uid() = user_id);

CREATE TRIGGER update_knowledge_points_updated_at BEFORE UPDATE ON public.knowledge_points FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
