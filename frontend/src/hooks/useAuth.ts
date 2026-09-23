import { useCallback, useEffect, useState } from "react";
import { API_PREFIX } from "@/config/api";

export interface AuthUser {
  id: string;
  email: string;
  display_name?: string | null;
  phone?: string | null;
  teaching_subject?: string | null;
  roles?: string[];
  job_title?: string | null;
  personal_email?: string | null;
  multi_project_admin?: boolean;
  ui_locale?: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  display_name?: string;
  role: string;
  teaching_subject?: string;
}

/** /auth/me 的结果：区分「令牌失效」与「后端/网络异常」，后者不该清登录态 */
type FetchMeResult =
  | { status: "ok"; user: AuthUser }
  | { status: "unauthorized" }
  | { status: "error" };

const TOKEN_KEY = "grade_buddy_access_token";

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [session, setSession] = useState<{ access_token: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async (token: string): Promise<FetchMeResult> => {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const res = await fetch(`${API_PREFIX}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        // 只有 401/403 才算令牌真的失效
        if (res.status === 401 || res.status === 403) {
          return { status: "unauthorized" };
        }
        if (res.ok) {
          const data = await res.json();
          return { status: "ok", user: data as AuthUser };
        }
        // 5xx：后端故障，不算令牌失效，稍后重试
      } catch {
        // 网络异常（后端重启中、断网）：同样保留令牌
      }
      if (attempt < 2) {
        await new Promise((resolve) => setTimeout(resolve, 600));
      }
    }
    return { status: "error" };
  }, []);

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setUser(null);
      setSession(null);
      setLoading(false);
      return;
    }

    fetchMe(token)
      .then((result) => {
        if (result.status === "ok") {
          setUser(result.user);
          setSession({ access_token: token });
        } else if (result.status === "unauthorized") {
          // 令牌确已过期/失效：清掉，ProtectedRoute 会自动跳登录页
          localStorage.removeItem(TOKEN_KEY);
          setUser(null);
          setSession(null);
        } else {
          // 后端异常/网络抖动：令牌留着，刷新页面即可恢复，不必重新登录
          setSession({ access_token: token });
        }
      })
      .finally(() => setLoading(false));
  }, [fetchMe]);

  const storeSession = (token: string, u: AuthUser) => {
    localStorage.setItem(TOKEN_KEY, token);
    setUser(u);
    setSession({ access_token: token });
  };

  const signIn = async (email: string, password: string) => {
    const res = await fetch(`${API_PREFIX}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = Array.isArray(data.detail)
        ? data.detail[0]?.msg
        : data.detail;
      return { error: { message: msg || "登录失败" } };
    }
    const token = data.access_token as string;
    const u = data.user as AuthUser;
    storeSession(token, u);
    return { error: null };
  };

  const register = async (payload: RegisterPayload) => {
    const res = await fetch(`${API_PREFIX}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = Array.isArray(data.detail)
        ? data.detail[0]?.msg
        : data.detail;
      return { error: { message: msg || "注册失败" } };
    }
    const token = data.access_token as string;
    const u = data.user as AuthUser;
    storeSession(token, u);
    return { error: null };
  };

  const signOut = async () => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setSession(null);
    return { error: null };
  };

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return;
    const result = await fetchMe(token);
    if (result.status === "ok") {
      setUser(result.user);
    } else if (result.status === "unauthorized") {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
      setSession(null);
    }
    // status === "error"：保留令牌与当前登录态，不做处理
  }, [fetchMe]);

  return { user, session, loading, signIn, register, signOut, refreshUser };
}
