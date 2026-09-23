import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchPublicBranding } from "@/services/multiProjectApi";

const DEFAULT_NAME = "叙阅";
const STORAGE_KEY = "project-brand-name";

type ProjectBrandingContextValue = {
  projectName: string;
  setProjectName: (name: string) => void;
  refreshBranding: () => Promise<void>;
};

const ProjectBrandingContext = createContext<ProjectBrandingContextValue | null>(null);

export function ProjectBrandingProvider({ children }: { children: ReactNode }) {
  const [projectName, setProjectNameState] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_NAME;
    } catch {
      return DEFAULT_NAME;
    }
  });

  const refreshBranding = useCallback(async () => {
    try {
      const data = await fetchPublicBranding();
      const name = (data.project_name || DEFAULT_NAME).trim() || DEFAULT_NAME;
      setProjectNameState(name);
      localStorage.setItem(STORAGE_KEY, name);
      document.title = name;
    } catch {
      /* keep cached */
    }
  }, []);

  useEffect(() => {
    void refreshBranding();
  }, [refreshBranding]);

  const setProjectName = useCallback((name: string) => {
    const cleaned = (name || DEFAULT_NAME).trim() || DEFAULT_NAME;
    setProjectNameState(cleaned);
    localStorage.setItem(STORAGE_KEY, cleaned);
    document.title = cleaned;
  }, []);

  const value = useMemo(
    () => ({ projectName, setProjectName, refreshBranding }),
    [projectName, setProjectName, refreshBranding],
  );

  return <ProjectBrandingContext.Provider value={value}>{children}</ProjectBrandingContext.Provider>;
}

export function useProjectBranding() {
  const ctx = useContext(ProjectBrandingContext);
  if (!ctx) {
    return {
      projectName: DEFAULT_NAME,
      setProjectName: () => {},
      refreshBranding: async () => {},
    };
  }
  return ctx;
}
