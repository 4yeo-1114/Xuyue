
-- Create storage bucket for teaching resources
INSERT INTO storage.buckets (id, name, public) VALUES ('teaching-resources', 'teaching-resources', true);

-- Storage policies: authenticated users can upload to their own folder
CREATE POLICY "Users can upload their own resources"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'teaching-resources' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can update their own resources"
ON storage.objects FOR UPDATE
USING (bucket_id = 'teaching-resources' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can delete their own resources"
ON storage.objects FOR DELETE
USING (bucket_id = 'teaching-resources' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Teaching resources are publicly accessible"
ON storage.objects FOR SELECT
USING (bucket_id = 'teaching-resources');

-- Create resources metadata table
CREATE TABLE public.teaching_resources (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  type TEXT NOT NULL DEFAULT '其他',
  file_url TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_size BIGINT NOT NULL DEFAULT 0,
  mime_type TEXT,
  tags TEXT[] DEFAULT '{}',
  uses INTEGER NOT NULL DEFAULT 0,
  rating NUMERIC(2,1) NOT NULL DEFAULT 0,
  is_shared BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

ALTER TABLE public.teaching_resources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own resources"
ON public.teaching_resources FOR SELECT
USING (auth.uid() = user_id OR is_shared = true);

CREATE POLICY "Users can create their own resources"
ON public.teaching_resources FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own resources"
ON public.teaching_resources FOR UPDATE
USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own resources"
ON public.teaching_resources FOR DELETE
USING (auth.uid() = user_id);

CREATE TRIGGER update_teaching_resources_updated_at
BEFORE UPDATE ON public.teaching_resources
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at_column();
