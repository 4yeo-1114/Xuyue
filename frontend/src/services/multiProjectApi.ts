import { API_PREFIX } from "@/config/api";
import { getAuthToken } from "@/services/api";

export type DbProfile = {
  id: string;
  name: string;
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
  created_at?: string;
  updated_at?: string;
  is_active?: boolean;
};

export type MultiProjectSettings = {
  project_name: string;
  active_db_profile_id?: string | null;
  active_db_profile?: DbProfile | null;
  db_profiles: DbProfile[];
  updated_at?: string;
};

async function authFetch(path: string, init?: RequestInit) {
  const token = await getAuthToken();
  if (!token) throw new Error("请先登录");
  const resp = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || data.message || `请求失败 (${resp.status})`);
  }
  return data;
}

export async function fetchPublicBranding(): Promise<{ project_name: string }> {
  const resp = await fetch(`${API_PREFIX}/branding`);
  if (!resp.ok) return { project_name: "叙阅" };
  return resp.json();
}

export async function fetchMultiProjectAccess(): Promise<{ allowed: boolean }> {
  const data = await authFetch("/multi-project/access");
  return data;
}

export async function fetchMultiProjectSettings(): Promise<MultiProjectSettings> {
  const data = await authFetch("/multi-project/settings");
  return data.data as MultiProjectSettings;
}

export async function updateProjectName(project_name: string): Promise<string> {
  const data = await authFetch("/multi-project/project-name", {
    method: "PUT",
    body: JSON.stringify({ project_name }),
  });
  return data.data.project_name as string;
}

export type DbProfileInput = {
  name: string;
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
};

export async function createDbProfile(body: DbProfileInput): Promise<DbProfile> {
  const data = await authFetch("/multi-project/db-profiles", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return data.data as DbProfile;
}

export async function updateDbProfile(id: string, body: DbProfileInput): Promise<DbProfile> {
  const data = await authFetch(`/multi-project/db-profiles/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return data.data as DbProfile;
}

export async function deleteDbProfile(id: string): Promise<void> {
  await authFetch(`/multi-project/db-profiles/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function applyDbProfile(id: string): Promise<{ message: string; active_profile: DbProfile }> {
  const data = await authFetch(`/multi-project/db-profiles/${encodeURIComponent(id)}/apply`, {
    method: "POST",
  });
  return data.data;
}
