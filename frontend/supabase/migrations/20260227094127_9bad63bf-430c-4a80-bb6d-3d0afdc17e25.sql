
-- Allow admins to read all profiles for user management
CREATE POLICY "Admins can view all profiles"
ON public.profiles FOR SELECT
TO authenticated
USING (public.is_any_admin(auth.uid()) OR auth.uid() = user_id);

-- Drop the old restrictive policy first
DROP POLICY IF EXISTS "Users can view their own profile" ON public.profiles;
