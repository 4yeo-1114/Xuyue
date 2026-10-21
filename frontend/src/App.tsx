import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useAuth } from "@/hooks/useAuth";
import { isPlatformAdmin } from "@/lib/adminAccess";
import { ProjectBrandingProvider } from "@/contexts/ProjectBrandingContext";
import { LocaleProvider, useLocale } from "@/contexts/LocaleContext";
import { BrandLogo } from "@/components/BrandLogo";
import Index from "./pages/Index";
import Auth from "./pages/Auth";
import Admin from "./pages/Admin";
import NotFound from "./pages/NotFound";
import DingTalkEntry from "./pages/DingTalkEntry";

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <LoadingScreen />;
  }

  if (!user) {
    return <Navigate to="/auth" replace />;
  }

  return <>{children}</>;
}

function AuthRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  // 1020：原来 loading 时 return null = 一整段纯白空窗，改走 LoadingScreen
  if (loading) return <LoadingScreen />;
  if (user) return <Navigate to="/" replace />;

  return <>{children}</>;
}

/** 仅系统管理员、子系统管理员可访问 /admin */
function AdminProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const { t } = useLocale();
  const deniedToastShown = useRef(false);

  useEffect(() => {
    if (
      !loading &&
      user &&
      !isPlatformAdmin(user) &&
      !deniedToastShown.current
    ) {
      deniedToastShown.current = true;
      toast.error(t("admin.denied"));
    }
  }, [loading, user, t]);

  if (loading) {
    return <LoadingScreen />;
  }

  if (!user) {
    return <Navigate to="/auth" replace />;
  }

  if (!isPlatformAdmin(user)) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <BrandLogo className="w-12 h-12 animate-pulse" alt="" />
    </div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ProjectBrandingProvider>
      <LocaleProvider>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <Routes>
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <Index />
                  </ProtectedRoute>
                }
              />
              {/* URL 路由化：/nav/:navId 对应侧边栏功能域（原 state 式 activeNavId） */}
              <Route
                path="/nav/:navId"
                element={
                  <ProtectedRoute>
                    <Index />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/auth"
                element={
                  <AuthRoute>
                    <Auth />
                  </AuthRoute>
                }
              />
              <Route
                path="/admin"
                element={
                  <AdminProtectedRoute>
                    <Admin />
                  </AdminProtectedRoute>
                }
              />
              {/* Legacy class route redirects to home */}
              <Route
                path="/class/:classId"
                element={<Navigate to="/" replace />}
              />
              {/* 钉钉工作台免登入口：放在登录校验外，由 DingTalkEntry 自行登录 */}
              <Route path="/dingtalk/entry" element={<DingTalkEntry />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </TooltipProvider>
      </LocaleProvider>
    </ProjectBrandingProvider>
  </QueryClientProvider>
);

export default App;
