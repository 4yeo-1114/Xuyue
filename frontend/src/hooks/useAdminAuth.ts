import { useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { supabase } from "@/integrations/supabase/client";

export type AdminRole = "super_admin" | "school_admin";

interface AdminAuthState {
  isAdmin: boolean;
  roles: AdminRole[];
  schoolId: string | null;
  loading: boolean;
}

export function useAdminAuth(): AdminAuthState & ReturnType<typeof useAuth> {
  const auth = useAuth();
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [schoolId, setSchoolId] = useState<string | null>(null);
  const [roleLoading, setRoleLoading] = useState(true);

  useEffect(() => {
    // Wait for auth to finish loading before checking user
    if (auth.loading) return;

    if (!auth.user) {
      setRoles([]);
      setSchoolId(null);
      setRoleLoading(false);
      return;
    }

    const fetchRoles = async () => {
      setRoleLoading(true);
      const { data, error } = await supabase
        .from("user_roles")
        .select("role, school_id")
        .eq("user_id", auth.user!.id);

      if (!error && data) {
        setRoles(data.map((r: any) => r.role as AdminRole));
        const schoolRole = data.find((r: any) => r.school_id);
        setSchoolId(schoolRole?.school_id ?? null);
      }
      setRoleLoading(false);
    };

    fetchRoles();
  }, [auth.user, auth.loading]);

  return {
    ...auth,
    isAdmin: roles.length > 0,
    roles,
    schoolId,
    loading: auth.loading || roleLoading,
  };
}
