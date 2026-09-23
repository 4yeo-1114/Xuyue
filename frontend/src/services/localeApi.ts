import { API_PREFIX } from "@/config/api";
import { getAuthToken } from "@/services/api";
import type { AppLocale } from "@/i18n/types";

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export async function fetchUserLocale(): Promise<AppLocale | null> {
  const res = await fetch(`${API_PREFIX}/auth/me`, {
    headers: await authHeaders(),
  });
  if (!res.ok) return null;
  const data = await res.json();
  const locale = String(data?.ui_locale || "zh").toLowerCase();
  return locale === "en" ? "en" : "zh";
}

export async function saveUserLocale(locale: AppLocale): Promise<AppLocale> {
  const res = await fetch(`${API_PREFIX}/auth/locale`, {
    method: "PATCH",
    headers: await authHeaders(),
    body: JSON.stringify({ locale }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = data?.detail || "Failed to save language preference";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  const data = await res.json();
  const saved = String(data?.ui_locale || locale).toLowerCase();
  return saved === "en" ? "en" : "zh";
}

export function localeStorageKey(userId?: string | null): string {
  return userId ? `grade_buddy_locale_${userId}` : "grade_buddy_locale_guest";
}
