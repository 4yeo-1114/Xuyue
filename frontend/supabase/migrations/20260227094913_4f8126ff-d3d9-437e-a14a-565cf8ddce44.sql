-- Fix circular dependency: allow users to read their own roles
DROP POLICY IF EXISTS "Admins can view all roles" ON public.user_roles;

-- Users can always see their own roles; admins can see all roles
CREATE POLICY "Users can view own roles, admins all"
ON public.user_roles FOR SELECT
TO authenticated
USING (auth.uid() = user_id OR is_any_admin(auth.uid()));
