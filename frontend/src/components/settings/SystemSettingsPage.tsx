import { useEffect, useMemo, useState } from "react";
import { Settings, KeyRound } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StorageCleanupSection } from "@/components/settings/StorageCleanupSection";
import { toast } from "sonner";
import { API_PREFIX, REQUEST_TIMEOUT, MAX_RETRIES } from "@/config/api";
import { useLocale } from "@/contexts/LocaleContext";

async function getAuthToken(): Promise<string | null> {
  const local = typeof localStorage !== "undefined" ? localStorage.getItem("grade_buddy_access_token") : null;
  return local || null;
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  retries = MAX_RETRIES,
  statusErrorFallback?: (status: number) => string,
): Promise<T> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
  try {
    const res = await fetch(`${API_PREFIX}${endpoint}`, { ...options, headers, signal: controller.signal });
    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({}));
      const msg = typeof errorBody.detail === "string" ? errorBody.detail : errorBody.message || (statusErrorFallback ? statusErrorFallback(res.status) : `Request failed: ${res.status}`);
      throw new Error(msg);
    }
    const j = await res.json();
    return (j?.data ?? j) as T;
  } catch (e) {
    if (retries > 0 && !(e instanceof DOMException)) {
      return request<T>(endpoint, options, retries - 1, statusErrorFallback);
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

type SystemSettingsOut = {
  can_edit_access_token: boolean;
  access_token_masked?: string | null;
  baidu_api_key_masked?: string | null;
  baidu_secret_key_masked?: string | null;
  baidu_auto_refresh_configured?: boolean;
  qwen_api_key_masked?: string | null;
  qwen_model?: string | null;
};

export function SystemSettingsPage() {
  const { user } = useAuth();
  const { t } = useLocale();
  const isAdmin = useMemo(() => {
    if (!user?.roles) return false;
    return user.roles.includes("系统管理员") || user.roles.includes("子系统管理员");
  }, [user?.roles]);

  const [loading, setLoading] = useState(false);
  const [tokenMasked, setTokenMasked] = useState<string | null>(null);
  const [accessToken, setAccessToken] = useState("");
  const [canEditToken, setCanEditToken] = useState(false);
  const [baiduApiKeyMasked, setBaiduApiKeyMasked] = useState<string | null>(null);
  const [baiduSecretKeyMasked, setBaiduSecretKeyMasked] = useState<string | null>(null);
  const [baiduApiKey, setBaiduApiKey] = useState("");
  const [baiduSecretKey, setBaiduSecretKey] = useState("");
  const [baiduAutoRefresh, setBaiduAutoRefresh] = useState(false);
  const [qwenKeyMasked, setQwenKeyMasked] = useState<string | null>(null);
  const [qwenApiKey, setQwenApiKey] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const data = await request<SystemSettingsOut>("/system-settings", {}, MAX_RETRIES, (s) => t("settings.system.requestFailed", { status: s }));
      setTokenMasked(data.access_token_masked ?? null);
      setBaiduApiKeyMasked(data.baidu_api_key_masked ?? null);
      setBaiduSecretKeyMasked(data.baidu_secret_key_masked ?? null);
      setBaiduAutoRefresh(!!data.baidu_auto_refresh_configured);
      setQwenKeyMasked(data.qwen_api_key_masked ?? null);
      setCanEditToken(!!data.can_edit_access_token);
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("settings.system.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const saveBaiduCredentials = async () => {
    const apiKey = baiduApiKey.trim();
    const secretKey = baiduSecretKey.trim();
    if (!apiKey && !secretKey) {
      toast.error(t("settings.system.baiduCredentialsRequired"));
      return;
    }
    if ((!apiKey && !baiduApiKeyMasked) || (!secretKey && !baiduSecretKeyMasked)) {
      toast.error(t("settings.system.baiduCredentialsBothRequired"));
      return;
    }
    setLoading(true);
    try {
      const data = await request<SystemSettingsOut>("/system-settings/baidu-credentials", {
        method: "PATCH",
        body: JSON.stringify({
          api_key: apiKey || undefined,
          secret_key: secretKey || undefined,
        }),
      }, MAX_RETRIES, (s) => t("settings.system.requestFailed", { status: s }));
      setBaiduApiKey("");
      setBaiduSecretKey("");
      setBaiduApiKeyMasked(data.baidu_api_key_masked ?? null);
      setBaiduSecretKeyMasked(data.baidu_secret_key_masked ?? null);
      setTokenMasked(data.access_token_masked ?? null);
      setBaiduAutoRefresh(!!data.baidu_auto_refresh_configured);
      toast.success(t("settings.system.baiduCredentialsUpdated"));
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("settings.system.updateFailed"));
    } finally {
      setLoading(false);
    }
  };

  const saveAccessToken = async () => {
    const tokenValue = (accessToken || "").trim();
    if (!tokenValue) {
      toast.error(t("settings.system.accessTokenRequired"));
      return;
    }
    setLoading(true);
    try {
      const data = await request<SystemSettingsOut>("/system-settings/baidu-access-token", {
        method: "PATCH",
        body: JSON.stringify({ access_token: tokenValue }),
      }, MAX_RETRIES, (s) => t("settings.system.requestFailed", { status: s }));
      setAccessToken("");
      setTokenMasked(data.access_token_masked ?? null);
      toast.success(t("settings.system.baiduUpdated"));
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("settings.system.updateFailed"));
    } finally {
      setLoading(false);
    }
  };

  const saveQwenSettings = async () => {
    const key = (qwenApiKey || "").trim();
    if (!key && !qwenKeyMasked) {
      toast.error(t("settings.system.qwenKeyRequired"));
      return;
    }
    setLoading(true);
    try {
      const data = await request<SystemSettingsOut>("/system-settings/qwen", {
        method: "PATCH",
        body: JSON.stringify({ api_key: key || undefined }),
      }, MAX_RETRIES, (s) => t("settings.system.requestFailed", { status: s }));
      setQwenApiKey("");
      setQwenKeyMasked(data.qwen_api_key_masked ?? null);
      toast.success(t("settings.system.qwenUpdated"));
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("settings.system.updateFailed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <Settings className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-foreground">{t("settings.system.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("settings.system.subtitle")}</p>
        </div>
      </div>

      <StorageCleanupSection />

      {isAdmin && canEditToken ? (
        <>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-primary" />
                {t("settings.system.baiduCredentials")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className={baiduAutoRefresh ? "text-sm text-emerald-600" : "text-sm text-amber-600"}>
                {baiduAutoRefresh
                  ? t("settings.system.baiduAutoRefreshEnabled")
                  : t("settings.system.baiduAutoRefreshDisabled")}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-sm">{t("settings.system.baiduApiKey")}</Label>
                  <Input
                    value={baiduApiKey}
                    onChange={(e) => setBaiduApiKey(e.target.value)}
                    placeholder={baiduApiKeyMasked || t("settings.system.baiduApiKeyPlaceholder")}
                    type="password"
                    autoComplete="new-password"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-sm">{t("settings.system.baiduSecretKey")}</Label>
                  <Input
                    value={baiduSecretKey}
                    onChange={(e) => setBaiduSecretKey(e.target.value)}
                    placeholder={baiduSecretKeyMasked || t("settings.system.baiduSecretKeyPlaceholder")}
                    type="password"
                    autoComplete="new-password"
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <Button onClick={() => void saveBaiduCredentials()} disabled={loading}>
                  {t("settings.system.saveBaiduCredentials")}
                </Button>
              </div>
              <div className="border-t pt-4 space-y-3">
                <div className="text-xs font-medium text-muted-foreground">
                  {t("settings.system.baiduTokenFallback")}
                </div>
                <div className="text-sm text-muted-foreground">
                  {t("settings.system.current", {
                    value: tokenMasked ? tokenMasked : t("settings.system.notSet"),
                  })}
                </div>
                <div className="space-y-2">
                  <Label className="text-sm">{t("settings.system.baiduUpdateLabel")}</Label>
                  <Input
                    value={accessToken}
                    onChange={(e) => setAccessToken(e.target.value)}
                    placeholder={t("settings.system.baiduPlaceholder")}
                    type="password"
                    autoComplete="new-password"
                  />
                </div>
                <div className="flex justify-end">
                  <Button onClick={() => void saveAccessToken()} disabled={loading}>
                    {t("settings.system.update")}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-primary" />
                {t("settings.system.qwenKey")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="text-sm text-muted-foreground">
                {t("settings.system.current", {
                  value: qwenKeyMasked ? qwenKeyMasked : t("settings.system.notSet"),
                })}
              </div>
              <div className="space-y-2">
                <Label className="text-sm">{t("settings.system.qwenApiKey")}</Label>
                <Input
                  value={qwenApiKey}
                  onChange={(e) => setQwenApiKey(e.target.value)}
                  placeholder={t("settings.system.qwenPlaceholder")}
                  type="password"
                />
              </div>
              <div className="flex justify-end">
                <Button onClick={() => void saveQwenSettings()} disabled={loading}>
                  {t("settings.system.saveQwen")}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
