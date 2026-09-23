
-- 1. Create role enum
CREATE TYPE public.app_role AS ENUM ('super_admin', 'school_admin');

-- 2. User roles table
CREATE TABLE public.user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  role app_role NOT NULL,
  school_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);

ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

-- 3. Security definer functions
CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role app_role)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id AND role = _role
  )
$$;

CREATE OR REPLACE FUNCTION public.is_any_admin(_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id
  )
$$;

-- 4. RLS for user_roles
CREATE POLICY "Admins can view all roles"
ON public.user_roles FOR SELECT
TO authenticated
USING (public.is_any_admin(auth.uid()));

CREATE POLICY "Super admins can insert roles"
ON public.user_roles FOR INSERT
TO authenticated
WITH CHECK (public.has_role(auth.uid(), 'super_admin'));

CREATE POLICY "Super admins can update roles"
ON public.user_roles FOR UPDATE
TO authenticated
USING (public.has_role(auth.uid(), 'super_admin'));

CREATE POLICY "Super admins can delete roles"
ON public.user_roles FOR DELETE
TO authenticated
USING (public.has_role(auth.uid(), 'super_admin'));

-- 5. System config table
CREATE TABLE public.system_config (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text UNIQUE NOT NULL,
  value jsonb NOT NULL DEFAULT '{}',
  label text NOT NULL DEFAULT '',
  category text NOT NULL DEFAULT 'general',
  description text NOT NULL DEFAULT '',
  updated_by uuid,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.system_config ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can view system config"
ON public.system_config FOR SELECT
TO authenticated
USING (public.is_any_admin(auth.uid()));

CREATE POLICY "Super admins can insert config"
ON public.system_config FOR INSERT
TO authenticated
WITH CHECK (public.has_role(auth.uid(), 'super_admin'));

CREATE POLICY "Admins can update config"
ON public.system_config FOR UPDATE
TO authenticated
USING (public.is_any_admin(auth.uid()));

CREATE POLICY "Super admins can delete config"
ON public.system_config FOR DELETE
TO authenticated
USING (public.has_role(auth.uid(), 'super_admin'));

-- 6. Feature flags table
CREATE TABLE public.feature_flags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text UNIQUE NOT NULL,
  label text NOT NULL DEFAULT '',
  enabled boolean NOT NULL DEFAULT true,
  scope text NOT NULL DEFAULT 'global',
  scope_id text,
  updated_by uuid,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.feature_flags ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read feature flags (needed for frontend integration)
CREATE POLICY "Authenticated users can view feature flags"
ON public.feature_flags FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Admins can insert feature flags"
ON public.feature_flags FOR INSERT
TO authenticated
WITH CHECK (public.is_any_admin(auth.uid()));

CREATE POLICY "Admins can update feature flags"
ON public.feature_flags FOR UPDATE
TO authenticated
USING (public.is_any_admin(auth.uid()));

CREATE POLICY "Admins can delete feature flags"
ON public.feature_flags FOR DELETE
TO authenticated
USING (public.is_any_admin(auth.uid()));

-- 7. Seed default system config
INSERT INTO public.system_config (key, value, label, category, description) VALUES
  ('ai_model', '"gemini-2.5-flash"', 'AI 模型', 'ai', '系统使用的 AI 模型'),
  ('grading_threshold', '60', '及格分数线', 'grading', '默认及格分数阈值'),
  ('push_frequency', '"daily"', '推送频率', 'push', '分层推送的默认频率'),
  ('default_school_level', '"初中"', '默认学段', 'general', '新建班级的默认学段'),
  ('max_students_per_class', '60', '班级人数上限', 'general', '每个班级的最大学生数');

-- 8. Seed default feature flags
INSERT INTO public.feature_flags (key, label, enabled) VALUES
  ('ai_review', '课堂讲评', true),
  ('ai_targeted', '靶向提升', true),
  ('ai_layered', '分层推送', true),
  ('smart_exam', '智能组卷', true),
  ('smart_gen', '智能生成', true),
  ('resource_lib', '资源库', true),
  ('knowledge_graph', '知识图谱', true),
  ('class_portrait', '班级画像', true),
  ('compare_analysis', '对比分析', true),
  ('question_analysis', '题目分析', true),
  ('prep_plan', '备课计划', true);
