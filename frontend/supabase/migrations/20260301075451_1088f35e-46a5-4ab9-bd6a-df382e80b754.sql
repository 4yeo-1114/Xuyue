
-- Add AI detection and cross-class columns to teaching_resources
ALTER TABLE public.teaching_resources
  ADD COLUMN IF NOT EXISTS detected_grade text,
  ADD COLUMN IF NOT EXISTS detected_class text,
  ADD COLUMN IF NOT EXISTS detected_subject text,
  ADD COLUMN IF NOT EXISTS detected_unit text,
  ADD COLUMN IF NOT EXISTS detected_chapter text,
  ADD COLUMN IF NOT EXISTS detected_school_level text,
  ADD COLUMN IF NOT EXISTS detection_confidence numeric DEFAULT 0,
  ADD COLUMN IF NOT EXISTS uploaded_from_class text,
  ADD COLUMN IF NOT EXISTS uploaded_from_grade text,
  ADD COLUMN IF NOT EXISTS is_cross_class boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS question_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS knowledge_point_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS difficulty numeric DEFAULT 0,
  ADD COLUMN IF NOT EXISTS source_label text DEFAULT '手动上传';
