import { cn } from "@/lib/utils";
import {
  ShieldAlert,
  FileText,
  Shield,
  LogOut,
  ChevronLeft,
  LucideIcon,
  Layers,
  ClipboardList,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageToggle } from "@/components/LanguageToggle";
import { useLocale } from "@/contexts/LocaleContext";

interface AdminNavItem {
  id: string;
  labelKey: string;
  icon: LucideIcon;
}

const BASE_ADMIN_NAV: AdminNavItem[] = [
  { id: "accounts", labelKey: "admin.nav.accounts", icon: ShieldAlert },
  {
    id: "teacher-grading",
    labelKey: "admin.nav.teacherGrading",
    icon: FileText,
  },
  {
    id: "flow-grading",
    labelKey: "admin.nav.flowGrading",
    icon: ClipboardList,
  },
];

const MULTI_PROJECT_NAV: AdminNavItem = {
  id: "multi-project",
  labelKey: "admin.nav.multiProject",
  icon: Layers,
};

interface AdminLayoutProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  onBack: () => void;
  onSignOut: () => void;
  roleLabel: string;
  userName: string;
  showMultiProject?: boolean;
  children: React.ReactNode;
}

export function AdminLayout({
  activeTab,
  onTabChange,
  onBack,
  onSignOut,
  roleLabel,
  userName,
  showMultiProject = false,
  children,
}: AdminLayoutProps) {
  const { t } = useLocale();
  const adminNav = showMultiProject
    ? [...BASE_ADMIN_NAV, MULTI_PROJECT_NAV]
    : BASE_ADMIN_NAV;

  return (
    <div className="flex h-screen overflow-x-auto overflow-y-hidden bg-background">
      <aside className="w-[220px] h-full bg-card border-r border-border flex flex-col shrink-0">
        <div className="p-5 border-b border-border shrink-0">
          <div className="flex items-center gap-2 mb-1">
            <Shield className="w-5 h-5 text-primary" />
            <h1 className="text-lg font-bold text-foreground">
              {t("admin.layout.title")}
            </h1>
          </div>
          <p className="text-xs text-muted-foreground truncate">{userName}</p>
          <p className="text-xs text-muted-foreground">{roleLabel}</p>
        </div>

        <nav className="flex-1 min-h-0 overflow-y-auto p-3">
          <ul className="space-y-0.5">
            {adminNav.map((item) => {
              const Icon = item.icon;
              const active = activeTab === item.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onTabChange(item.id)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                      active
                        ? "bg-primary/10 text-primary font-semibold"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon className="w-[18px] h-[18px] shrink-0" />
                    <span>{t(item.labelKey)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="p-3 border-t border-border space-y-1 shrink-0 bg-card">
          <LanguageToggle className="w-full justify-center" />
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2"
            onClick={onBack}
          >
            <ChevronLeft className="w-4 h-4" /> {t("admin.layout.backToApp")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2 text-destructive hover:text-destructive"
            onClick={onSignOut}
          >
            <LogOut className="w-4 h-4" /> {t("admin.layout.signOut")}
          </Button>
        </div>
      </aside>

      <main className="flex-1 min-h-0 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
