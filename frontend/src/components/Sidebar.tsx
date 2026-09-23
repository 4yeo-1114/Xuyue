import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import {
  Home,
  Users2,
  BarChart3,
  BrainCircuit,
  BookOpen,
  Building2,
  Settings,
  LayoutDashboard,
  UserSquare2,
  Network,
  PieChart,
  ListChecks,
  GitCompare,
  Presentation,
  Target,
  Layers,
  Library,
  Video,
  FileText,
  ClipboardList,
  FolderCog,
  BookMarked,
  BookCopy,
  UserCog,
  Download,
  ChevronDown,
  PenTool,
  History,
  User,
  Power,
  LucideIcon,
  School,
  Shield,
  Wind,
  Sparkles,
  BellRing,
  LayoutGrid,
  FolderTree,
  Utensils,
  Users,
  Receipt,
  BarChart4,
} from "lucide-react";
import { toast } from "sonner";
import { exitPackagedApp } from "@/services/gradingApi";
import { isPlatformAdmin, isSchoolAdmin, isParent } from "@/lib/adminAccess";
import { useProjectBranding } from "@/contexts/ProjectBrandingContext";
import { BrandLogo } from "@/components/BrandLogo";
import { useLocale } from "@/contexts/LocaleContext";
import { useFeatureFlags } from "@/hooks/useFeatureFlags";

/* ── Nav structure ── */
export interface NavChild {
  id: string;
  label: string;
  icon: LucideIcon;
  adminOnly?: boolean;
  /** 仅家长角色可见（家长端入口） */
  parentOnly?: boolean;
  /** 对应后端功能开关 key（E08）；enabled=false 时隐藏该入口 */
  featureKey?: string;
}

export interface NavGroup {
  id: string;
  label: string;
  icon: LucideIcon;
  children?: NavChild[];
}

export const NAV_ITEMS: NavGroup[] = [
  { id: "home", label: "首页", icon: Home },
  { id: "whats-new", label: "新功能", icon: Sparkles },
  {
    id: "my-classes",
    label: "我的班级",
    icon: Users2,
    children: [
      { id: "class-dashboard", label: "班级看板", icon: LayoutDashboard },
      { id: "settings-class", label: "班级管理", icon: FolderCog },
    ],
  },
  {
    id: "analytics",
    label: "学情分析",
    icon: BarChart3,
    children: [
      { id: "class-students", label: "学生分析", icon: UserSquare2 },
      { id: "analytics-portrait", label: "班级分析", icon: PieChart },
      { id: "analytics-grade", label: "年级分析", icon: PieChart },
      { id: "analytics-questions", label: "题目分析", icon: ListChecks },
      { id: "analytics-compare", label: "班级对比", icon: GitCompare },
      { id: "class-knowledge", label: "知识图谱", icon: Network },
    ],
  },
  {
    id: "ai-teaching",
    label: "AI精准教学",
    icon: BrainCircuit,
    children: [
      {
        id: "ai-review",
        label: "课堂讲评",
        icon: Presentation,
        featureKey: "ai_review",
      },
      {
        id: "ai-targeted",
        label: "靶向提升",
        icon: Target,
        featureKey: "ai_targeted",
      },
      {
        id: "ai-layered",
        label: "分层推送",
        icon: Layers,
        featureKey: "ai_layered",
      },
    ],
  },
  {
    id: "ai-prep",
    label: "AI备课",
    icon: BookOpen,
    children: [
      { id: "prep-matrix", label: "四维定位矩阵", icon: LayoutGrid },
      { id: "prep-catalog", label: "教材目录", icon: FolderTree },
      { id: "prep-bank", label: "备课计划", icon: Library },
      { id: "prep-lesson", label: "教案生成", icon: BookMarked },
      {
        id: "prep-compose",
        label: "智能生成",
        icon: Sparkles,
        featureKey: "smart_gen",
      },
      {
        id: "prep-exam",
        label: "智能组卷",
        icon: FileText,
        featureKey: "smart_exam",
      },
      { id: "prep-video", label: "资源库", icon: Video },
      { id: "prep-question-bank", label: "题库", icon: BookCopy },
    ],
  },
  {
    id: "grading",
    label: "作业批改",
    icon: PenTool,
    children: [
      {
        id: "grading-start",
        label: "开始批改",
        icon: PenTool,
        featureKey: "ai_grading",
      },
      {
        id: "grading-history",
        label: "批改历史",
        icon: History,
        featureKey: "ai_grading",
      },
      {
        id: "grading-errors",
        label: "批改详细",
        icon: FileText,
        featureKey: "ai_grading",
      },
      {
        id: "flow-tasks",
        label: "流水阅卷",
        icon: ClipboardList,
      },
    ],
  },
  {
    id: "student-growth",
    label: "学生成长",
    icon: Wind,
    children: [
      { id: "wuyu-profile", label: "成长档案", icon: UserSquare2 },
      { id: "assessment", label: "多元评价", icon: ListChecks },
      { id: "student-ops", label: "激励中心", icon: Layers },
    ],
  },
  {
    id: "parent",
    label: "家长",
    icon: Users,
    children: [
      { id: "parent-wuyu", label: "孩子五育画像", icon: UserSquare2, parentOnly: true },
    ],
  },
  {
    id: "school-admin",
    label: "学校管理",
    icon: School,
    children: [
      {
        id: "school-dashboard",
        label: "学校驾驶舱",
        icon: LayoutDashboard,
        adminOnly: true,
      },
      {
        id: "school-warning",
        label: "预警中心",
        icon: BellRing,
        adminOnly: true,
      },
      {
        id: "canteen-ledger",
        label: "食堂台账",
        icon: Utensils,
      },
    ],
  },
  {
    id: "bureau",
    label: "教育局",
    icon: Building2,
    children: [
      {
        id: "bureau-dashboard",
        label: "教育局驾驶舱",
        icon: LayoutDashboard,
        adminOnly: true,
      },
      {
        id: "bureau-center",
        label: "指挥中心",
        icon: ListChecks,
        adminOnly: true,
      },
    ],
  },
  {
    id: "settings",
    label: "设置",
    icon: Settings,
    children: [
      { id: "settings-personal", label: "个人设置", icon: User },
      { id: "settings-subject", label: "学科配置", icon: BookOpen },
      { id: "settings-hardware", label: "硬件配置", icon: UserCog },
      { id: "settings-multi-device", label: "多端管理", icon: Download },
      { id: "settings-preferences", label: "系统设置", icon: Settings },
      { id: "settings-teacher", label: "教师管理", icon: UserCog },
      { id: "settings-exam", label: "考试管理", icon: ClipboardList },
    ],
  },
  {
    id: "system-ops",
    label: "系统运营",
    icon: BarChart4,
    children: [
      { id: "scan-consumption", label: "扫描消耗", icon: Receipt },
      { id: "usage-summary", label: "用量汇总", icon: BarChart4 },
    ],
  },
];

/* ── 视觉分组：将顶级组归入小节（仅视觉呈现，不改 NAV_ITEMS 的 id 契约） ── */
interface NavSection {
  key: string;
  label: { zh: string; en: string };
  items: string[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    key: "workspace",
    label: { zh: "工作台", en: "Workspace" },
    items: ["home", "whats-new", "my-classes", "analytics"],
  },
  {
    key: "teaching",
    label: { zh: "教学工具", en: "Teaching Tools" },
    items: ["ai-teaching", "ai-prep", "grading"],
  },
  {
    key: "growth",
    label: { zh: "学生成长", en: "Student Growth" },
    items: ["student-growth"],
  },
  {
    key: "parent",
    label: { zh: "家长", en: "Parent" },
    items: ["parent"],
  },
  {
    key: "school",
    label: { zh: "学校管理", en: "School" },
    items: ["school-admin"],
  },
  {
    key: "bureau",
    label: { zh: "教育局", en: "Education Bureau" },
    items: ["bureau"],
  },
  { key: "system", label: { zh: "系统", en: "System" }, items: ["settings"] },
  {
    key: "system-ops",
    label: { zh: "系统运营", en: "Operations" },
    items: ["system-ops"],
  },
];

/* ── Persistence keys ── */
const STORAGE_KEY_EXPANDED = "sidebar-expanded-groups";

/* ── Component ── */
interface SidebarProps {
  className?: string;
  activeNavId: string;
  onNavChange: (id: string) => void;
}

export function Sidebar({ className, activeNavId, onNavChange }: SidebarProps) {
  const { user } = useAuth();
  const { projectName } = useProjectBranding();
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_EXPANDED);
      return saved ? new Set(JSON.parse(saved)) : new Set<string>();
    } catch {
      return new Set<string>();
    }
  });

  const isAdmin = useMemo(() => isPlatformAdmin(user), [user]);
  const isSchoolAdminUser = useMemo(() => isSchoolAdmin(user), [user]);
  const isParentUser = useMemo(() => isParent(user), [user]);

  const { data: featureFlags } = useFeatureFlags();
  const disabledFeatureKeys = useMemo(() => {
    const set = new Set<string>();
    (featureFlags ?? []).forEach((f) => {
      if (!f.enabled) set.add(f.key);
    });
    return set;
  }, [featureFlags]);

  // Persist expanded state
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY_EXPANDED,
        JSON.stringify([...expandedGroups]),
      );
    } catch {
      // 隐私模式/存储满时静默降级，与读路径一致
    }
  }, [expandedGroups]);

  const toggleGroup = useCallback((groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }, []);

  const isActive = (id: string) => activeNavId === id;

  // Check if any child of a group is active
  const isGroupActive = (group: NavGroup) =>
    group.children?.some((c) => c.id === activeNavId) ?? false;

  const filteredNavItems = useMemo(() => {
    return NAV_ITEMS.map((group) => {
      if (!group.children) return group;
      return {
        ...group,
        children: group.children.filter(
          (child) =>
            (child.parentOnly
              ? isParentUser
              : child.id === "school-dashboard" || child.id === "school-warning"
                ? isSchoolAdminUser
                : !child.adminOnly || isAdmin) &&
            (!child.featureKey || !disabledFeatureKeys.has(child.featureKey)),
        ),
      };
    }).filter((group) => !group.children || group.children.length > 0);
  }, [isAdmin, isSchoolAdminUser, isParentUser, disabledFeatureKeys]);

  // 按 section 编排顶级组（id → NavGroup 映射，便于按 SECTIONS 顺序渲染）
  const navById = useMemo(() => {
    const map = new Map<string, NavGroup>();
    filteredNavItems.forEach((g) => map.set(g.id, g));
    return map;
  }, [filteredNavItems]);

  return (
    <aside
      data-tour="sidebar"
      className={cn(
        "side-nav w-[224px] h-screen bg-sidebar text-sidebar-foreground border-r border-sidebar-border flex flex-col shrink-0 overflow-hidden shadow-[2px_0_12px_-6px_rgba(148,163,184,0.25)]",
        className,
      )}
    >
      {/* Logo 品牌区 */}
      <div className="px-5 pt-4 pb-4 border-b border-sidebar-border/70 flex items-center gap-2.5">
        <BrandLogo
          className="w-8 h-8 rounded-lg bg-white"
          alt={projectName}
        />
        <div className="min-w-0">
          <h1 className="text-[15px] font-bold text-sidebar-foreground truncate leading-tight">
            {projectName}
          </h1>
          <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
            {t("app.tagline")}
          </p>
        </div>
      </div>

      {/* 分组导航 */}
      <nav className="flex-1 px-3 pt-3 pb-4 overflow-y-auto sidebar-scrollbar">
        <ul>
          {NAV_SECTIONS.map((section, si) => {
            const groups = section.items
              .map((id) => navById.get(id))
              .filter((g): g is NavGroup => !!g);
            if (groups.length === 0) return null;
            const isGrowth = section.key === "growth";
            const label = section.label[locale === "en" ? "en" : "zh"];

            return (
              <li key={section.key} className={si === 0 ? "mt-0.5" : "mt-6"}>
                {/* 小节标题 */}
                <div className="px-3 mb-1.5">
                  {isGrowth ? (
                    <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-primary">
                      <span className="w-1 h-1 rounded-full bg-primary" />
                      {label}
                    </span>
                  ) : (
                    <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground/60">
                      {label}
                    </span>
                  )}
                </div>

                <ul className="space-y-0.5">
                  {groups.map((item) => {
                    const Icon = item.icon;
                    const hasChildren = !!item.children?.length;
                    const expanded = expandedGroups.has(item.id);
                    const groupActive = isGroupActive(item);
                    const selfActive = isActive(item.id);
                    const rowActive = selfActive || (groupActive && !expanded);
                    const rowTinted = groupActive && expanded;

                    return (
                      <li key={item.id}>
                        {/* Top-level button */}
                        <button
                          onClick={() => {
                            if (hasChildren) {
                              toggleGroup(item.id);
                            } else {
                              onNavChange(item.id);
                            }
                          }}
                          className={cn(
                            "w-full flex items-center gap-3 pl-3 pr-2.5 py-2 rounded-lg text-[13.5px] font-medium transition-colors duration-200 relative",
                            rowActive && "bg-primary/10 text-primary",
                            rowTinted && "text-primary/80",
                            !rowActive &&
                              !rowTinted &&
                              "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                          )}
                        >
                          {rowActive && (
                            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-full bg-primary" />
                          )}
                          <Icon
                            className="w-[18px] h-[18px] shrink-0"
                            strokeWidth={1.75}
                          />
                          <span
                            className={cn(
                              "flex-1 text-left truncate",
                              rowActive && "font-semibold",
                            )}
                          >
                            {t(`nav.${item.id}`, undefined, item.label)}
                          </span>
                          {hasChildren && (
                            <ChevronDown
                              className={cn(
                                "w-4 h-4 shrink-0 text-muted-foreground/70 transition-transform duration-200",
                                expanded && "rotate-180",
                              )}
                              strokeWidth={1.75}
                            />
                          )}
                        </button>

                        {/* Children */}
                        {hasChildren && expanded && (
                          <ul className="mt-0.5 space-y-0.5">
                            {item.children!.map((child) => {
                              const ChildIcon = child.icon;
                              const childActive = isActive(child.id);
                              return (
                                <li key={child.id}>
                                  <button
                                    onClick={() => onNavChange(child.id)}
                                    className={cn(
                                      "w-full flex items-center gap-2.5 pl-10 pr-2.5 py-1.5 rounded-md text-[13px] transition-colors duration-200",
                                      childActive
                                        ? "bg-primary/10 text-primary font-medium"
                                        : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                                    )}
                                  >
                                    <ChildIcon
                                      className={cn(
                                        "w-4 h-4 shrink-0",
                                        childActive
                                          ? "text-primary"
                                          : "text-muted-foreground/70",
                                      )}
                                      strokeWidth={1.75}
                                    />
                                    <span className="flex-1 text-left truncate">
                                      {t(
                                        `nav.${child.id}`,
                                        undefined,
                                        child.label,
                                      )}
                                    </span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 底部：管理 / 退出 */}
      <div className="p-3 border-t border-sidebar-border/60 bg-sidebar">
        <div className="space-y-1">
          {isAdmin && (
            <button
              type="button"
              onClick={() => navigate("/admin")}
              className="w-full flex items-center gap-3 pl-3 pr-2.5 py-2 rounded-lg text-[13px] font-medium text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors duration-200"
            >
              <Shield
                className="w-[18px] h-[18px] shrink-0"
                strokeWidth={1.75}
              />
              <span className="flex-1 text-left truncate">
                {t("admin.layout.title")}
              </span>
            </button>
          )}
          <button
            onClick={async () => {
              try {
                const res = await exitPackagedApp();
                if (res?.ok) {
                  toast.success(
                    t("sidebar.exitSuccess", { name: projectName }),
                  );
                } else {
                  toast.error(res?.msg || t("sidebar.exitFailed"));
                }
              } catch (e: any) {
                const msg = String(e?.message || "");
                if (msg.includes("仅打包版支持")) {
                  toast.error(t("sidebar.exitDevOnly"));
                  return;
                }
                toast.error(msg || t("sidebar.exitFailed"));
              }
            }}
            className="w-full flex items-center gap-3 pl-3 pr-2.5 py-2 rounded-lg text-[13px] font-medium text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors duration-200"
          >
            <Power className="w-[18px] h-[18px] shrink-0" strokeWidth={1.75} />
            <span className="flex-1 text-left truncate">
              {t("sidebar.exitApp", { name: projectName })}
            </span>
          </button>
        </div>
      </div>
    </aside>
  );
}
