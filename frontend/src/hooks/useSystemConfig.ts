import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";

interface SystemConfig {
  id: string;
  key: string;
  value: any;
  label: string;
  category: string;
  description: string;
  updated_by: string | null;
  updated_at: string;
}

export function useSystemConfig() {
  return useQuery({
    queryKey: ["system-config"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("system_config")
        .select("*")
        .order("category, key");
      if (error) throw error;
      return data as SystemConfig[];
    },
    staleTime: 60_000,
  });
}

export function useUpdateSystemConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, value }: { key: string; value: any }) => {
      const { error } = await supabase
        .from("system_config")
        .update({ value, updated_at: new Date().toISOString() })
        .eq("key", key);
      if (error) throw error;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["system-config"] }),
  });
}
