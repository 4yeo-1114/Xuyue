import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { isPlatformAdmin } from "@/lib/adminAccess";
import { cn } from "@/lib/utils";
import { AdminLayout } from "@/components/admin/AdminLayout";
import { AdminDashboard } from "@/components/admin/AdminDashboard";
import { AdminUsers } from "@/components/admin/AdminUsers";
import { AdminConfig } from "@/components/admin/AdminConfig";
import { AdminFeatures } from "@/components/admin/AdminFeatures";
import { AdminCompliancePage } from "@/components/admin/AdminCompliancePage";
import { AdminRightsPage } from "@/components/admin/AdminRightsPage";
import { AccountManagePage } from "@/components/settings/account-manage/AccountManagePage";
import { AdminTeacherGradingPage } from "@/components/admin/AdminTeacherGradingPage";
import { AdminFlowGradingPage } from "@/components/admin/AdminFlowGradingPage";
import { AdminMultiProjectPage } from "@/components/admin/AdminMultiProjectPage";
import { AdminQuotaPage } from "@/components/quota/AdminQuotaPage";
import { isMultiProjectAdmin } from "@/lib/multiProjectAccess";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSystemRole } from "@/i18n/index";
import {
  LayoutDashboard,
  Users2,
  Settings2,
  ToggleLeft,
  ShieldCheck,
  UserCheck,
  Coins,
  LucideIcon,
} from "lucide-react";

/* 后台子页面导航（原为孤儿组件，在此接线可达） */
interface AdminSubTab {
  id: string;
  labelKey: string;
  icon: LucideIcon;
  Page: () => React.ReactElement;
}

/* 左侧叶子 tab(独立功能页,不承载后台子页):这些 tab 下不显示 dashboard/users/config/features 子页导航 */
const SUB_PAGE_LESS_TABS = new Set(["teacher-grading", "flow-grading", "multi-project"]);

const ADMIN_SUB_TABS: AdminSubTab[] = [
  {
    id: "dashboard",
    labelKey: "admin.dashboard.title",
    icon: LayoutDashboard,
    Page: AdminDashboard,
  },
  {
    id: "users",
    labelKey: "admin.users.title",
    icon: Users2,
    Page: AdminUsers,
  },
  {
    id: "config",
    labelKey: "admin.config.title",
    icon: Settings2,
    Page: AdminConfig,
  },
  {
    id: "features",
    labelKey: "admin.features.title",
    icon: ToggleLeft,
    Page: AdminFeatures,
  },
  {
    id: "compliance",
    labelKey: "admin.compliance.title",
    icon: ShieldCheck,
    Page: AdminCompliancePage,
  },
  {
    id: "rights",
    labelKey: "admin.rights.title",
    icon: UserCheck,
    Page: AdminRightsPage,
  },
  {
    id: "quota",
    labelKey: "admin.quota.title",
    icon: Coins,
    Page: AdminQuotaPage,
  },
];

export default function Admin() {
  const { user, signOut } = useAuth();
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("accounts");
  const [activeSubTab, setActiveSubTab] = useState<string | null>(null);

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    setActiveSubTab(null);
  };

  const handleSubTabChange = (id: string) => {
    setActiveSubTab((prev) => (prev === id ? null : id));
  };

  const roleLabel = useMemo(() => {
    if (!user?.roles?.length) return t("admin.role.fallback");
    if (user.roles.includes("系统管理员"))
      return translateSystemRole(locale, "系统管理员");
    if (user.roles.includes("子系统管理员"))
      return translateSystemRole(locale, "子系统管理员");
    return translateSystemRole(locale, user.roles[0]);
  }, [user, t, locale]);

  if (!user || !isPlatformAdmin(user)) {
    return null;
  }

  const showMultiProject = isMultiProjectAdmin(user);

  const renderContent = () => {
    switch (activeTab) {
      case "accounts":
        return <AccountManagePage />;
      case "teacher-grading":
        return <AdminTeacherGradingPage />;
      case "flow-grading":
        return <AdminFlowGradingPage />;
      case "multi-project":
        return showMultiProject ? (
          <AdminMultiProjectPage />
        ) : (
          <AccountManagePage />
        );
      default:
        return <AccountManagePage />;
    }
  };

  const activeSubPage = activeSubTab
    ? (ADMIN_SUB_TABS.find((x) => x.id === activeSubTab) ?? null)
    : null;

  // 子页导航栏只在承载后台子页的左侧 tab 下显示;老师批改/多项目为独立功能页,不显示无关子页导航
  const showSubNav = !SUB_PAGE_LESS_TABS.has(activeTab);

  return (
    <AdminLayout
      activeTab={activeTab}
      onTabChange={handleTabChange}
      onBack={() => navigate("/")}
      onSignOut={async () => {
        await signOut();
        navigate("/auth");
      }}
      roleLabel={roleLabel}
      userName={user.display_name || user.email || t("admin.role.fallback")}
      showMultiProject={showMultiProject}
    >
      <div className="space-y-6">
        {/* 后台子页面导航(仅承载子页的左侧 tab 下显示) */}
        {showSubNav && (
          <div className="flex flex-wrap items-center gap-1 border-b border-border pb-3">
            {ADMIN_SUB_TABS.map(({ id, labelKey, icon: Icon }) => {
              const active = activeSubTab === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleSubTabChange(id)}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {t(labelKey)}
                </button>
              );
            })}
          </div>
        )}

        {activeSubPage && showSubNav ? <activeSubPage.Page /> : renderContent()}
      </div>
    </AdminLayout>
  );
}
