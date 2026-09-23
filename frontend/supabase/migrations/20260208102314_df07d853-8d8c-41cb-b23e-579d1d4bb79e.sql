
-- 考试记录表
CREATE TABLE public.exams (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  class_id UUID NOT NULL REFERENCES public.classes(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  title TEXT NOT NULL,
  total_score NUMERIC NOT NULL DEFAULT 100,
  exam_date DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.exams ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own exams" ON public.exams FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create their own exams" ON public.exams FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own exams" ON public.exams FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own exams" ON public.exams FOR DELETE USING (auth.uid() = user_id);

CREATE TRIGGER update_exams_updated_at BEFORE UPDATE ON public.exams
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE INDEX idx_exams_class_id ON public.exams(class_id);
CREATE INDEX idx_exams_user_id ON public.exams(user_id);

-- 学生考试成绩表
CREATE TABLE public.exam_scores (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  exam_id UUID NOT NULL REFERENCES public.exams(id) ON DELETE CASCADE,
  student_id UUID NOT NULL REFERENCES public.students(id) ON DELETE CASCADE,
  score NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(exam_id, student_id)
);

ALTER TABLE public.exam_scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own exam_scores" ON public.exam_scores FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create their own exam_scores" ON public.exam_scores FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own exam_scores" ON public.exam_scores FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own exam_scores" ON public.exam_scores FOR DELETE USING (auth.uid() = user_id);

CREATE TRIGGER update_exam_scores_updated_at BEFORE UPDATE ON public.exam_scores
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE INDEX idx_exam_scores_exam_id ON public.exam_scores(exam_id);
CREATE INDEX idx_exam_scores_student_id ON public.exam_scores(student_id);

-- 错题库
CREATE TABLE public.wrong_questions (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  student_id UUID NOT NULL REFERENCES public.students(id) ON DELETE CASCADE,
  class_id UUID NOT NULL REFERENCES public.classes(id) ON DELETE CASCADE,
  subject TEXT NOT NULL,
  question_content TEXT NOT NULL,
  correct_answer TEXT,
  student_answer TEXT,
  error_type TEXT NOT NULL DEFAULT 'other',
  analysis TEXT,
  exam_id UUID REFERENCES public.exams(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.wrong_questions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own wrong_questions" ON public.wrong_questions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create their own wrong_questions" ON public.wrong_questions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own wrong_questions" ON public.wrong_questions FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own wrong_questions" ON public.wrong_questions FOR DELETE USING (auth.uid() = user_id);

CREATE TRIGGER update_wrong_questions_updated_at BEFORE UPDATE ON public.wrong_questions
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE INDEX idx_wrong_questions_student_id ON public.wrong_questions(student_id);
CREATE INDEX idx_wrong_questions_class_id ON public.wrong_questions(class_id);
