import { useQuery } from "@tanstack/react-query";
import { getFeatureFlags } from "@/services/api";

export function useFeatureFlags() {
  return useQuery({
    queryKey: ["feature-flags"],
    queryFn: getFeatureFlags,
    staleTime: 60_000,
  });
}

export function useIsFeatureEnabled(key: string): boolean {
  const { data } = useFeatureFlags();
  if (!data) return true; // default to enabled if not loaded
  const flag = data.find((f) => f.key === key);
  return flag?.enabled ?? true;
}
