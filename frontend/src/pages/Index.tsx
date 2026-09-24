import { useState, useRef, useEffect, useMemo, Suspense, lazy } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { isPlatformAdmin, isParent, isNavPageAllowed } from "@/lib/adminAccess";
import { NAV_ITEMS, Sidebar } from "@/components/Sidebar";
import { TopHeader } from "@/components/TopHeader";
import { ClassManageDialog } from "@/components/ClassManageDialog";
import { StudentManageDialog } from "@/components/StudentManageDialog";
import { useClasses, ClassRecord } from "@/hooks/useClasses";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { useFeatureFlags, useIsFeatureEnabled } from "@/hooks/useFeatureFlags";
import { Button } from "@/components/ui/button";
import { GradingEntrySection } from "@/components/home/GradingEntrySection";
import { PhotoGradingDialog } from "@/components/home/PhotoGradingDialog";
import { StatsOverview } from "@/components/home/StatsOverview";
import { StudentMatrixPreview } from "@/components/home/StudentMatrixPreview";
import { TodoAndQuickActions } from "@/components/home/TodoAndQuickActions";
import { OnboardingTour } from "@/components/home/OnboardingTour";
import { GlobalSearchBar } from "@/components/home/GlobalSearchBar";
import { NewFeaturesPage } from "@/components/new-features/NewFeaturesPage";
import { ClassDashboard } from "@/components/class-detail/ClassDashboard";
import { StudentPanoramaPage } from "@/components/class-detail/StudentPanoramaPage";
import { ClassPortraitPage } from "@/components/class-detail/ClassPortraitPage";
import { ClassReviewPage } from "@/components/class-detail/ClassReviewPage";
import { TargetedImprovePage } from "@/components/class-detail/TargetedImprovePage";
import { LayeredPushPage } from "@/components/class-detail/LayeredPushPage";
import { ClassManagePage } from "@/components/settings/class-manage/ClassManagePage";
import { SubjectConfigPage } from "@/components/settings/subject-config/SubjectConfigPage";
import { PersonalSettingsPage } from "@/components/settings/settings-personal/PersonalSettingsPage";
import { SystemSettingsPage } from "@/components/settings/SystemSettingsPage";
import { HardwareConfigPage } from "@/components/settings/hardware/HardwareConfigPage";
import { PrepPlanPage } from "@/components/prep-plan/PrepPlanPage";
import { LessonPlanPage } from "@/components/prep-plan/LessonPlanPage";
import { PrepMatrixPage } from "@/components/prep-plan/PrepMatrixPage";
import { TextbookCatalogPage } from "@/components/prep-plan/TextbookCatalogPage";
import { CanteenLedgerPage } from "@/components/canteen/CanteenLedgerPage";
import { SmartGenPage } from "@/components/smart-gen/SmartGenPage";
import { ResourceLibPage } from "@/components/resource-lib/ResourceLibPage";
import { QuestionBankPage } from "@/components/question-bank/QuestionBankPage";
import { ResourceUploadDialog } from "@/components/resource-lib/ResourceUploadDialog";
import { GradingHistoryPage } from "@/components/grading/GradingHistoryPage";
import { ErrorBookPage } from "@/components/grading/ErrorBookPage";
import { FlowTeacherTasksPage } from "@/components/grading/flow/FlowTeacherTasksPage";
import { WuyuProfilePage } from "@/components/wuyu-profile/WuyuProfilePage";
import { AssessmentPage } from "@/components/assessment/AssessmentPage";
import { StudentOpsPage } from "@/components/student-ops/StudentOpsPage";
import { ParentPortalPage } from "@/components/parent/ParentPortal";
import { FloatingChat } from "@/components/FloatingChat";
import { ContentBreadcrumb } from "@/components/ContentBreadcrumb";
import { useLocale } from "@/contexts/LocaleContext";
import {
  FileText,
  Users2,
  PieChart,
  ListChecks,
  GitCompare,
  Presentation,
  Target,
  Layers,
  Library,
  FileStack,
  Video,
  FolderCog,
  BookMarked,
  UserCog,
  Settings,
  LayoutDashboard,
  UserSquare2,
  Network,
  ShieldOff,
  Loader2,
  Camera,
  Upload,
  ScanLine,
  ArrowRight,
} from "lucide-react";

const STORAGE_KEY_ACTIVE = "sidebar-active-nav";

const NO_TEACHING_FILTER_IDS = ["school-dashboard", "school-warning"] as const;

/* ── 懒加载体积大的功能域，降低首屏 bundle 体积 ── */
const GradeAnalysisPage = lazy(() =>
  import("@/components/class-detail/GradeAnalysisPage").then((m) => ({
    default: m.GradeAnalysisPage,
  })),
);
const QuestionAnalysisPage = lazy(() =>
  import("@/components/class-detail/QuestionAnalysisPage").then((m) => ({
    default: m.QuestionAnalysisPage,
  })),
);
const CompareAnalysisPage = lazy(() =>
  import("@/components/class-detail/CompareAnalysisPage").then((m) => ({
    default: m.CompareAnalysisPage,
  })),
);
const KnowledgeGraphPage = lazy(() =>
  import("@/components/class-detail/KnowledgeGraphPage").then((m) => ({
    default: m.KnowledgeGraphPage,
  })),
);
const ExamGenPage = lazy(() =>
  import("@/components/smart-exam/ExamGenPage").then((m) => ({
    default: m.ExamGenPage,
  })),
);
const GradingStartPage = lazy(() =>
  import("@/components/grading/GradingStartPage").then((m) => ({
    default: m.GradingStartPage,
  })),
);
const SchoolDashboardPage = lazy(() =>
  import("@/pages/SchoolDashboardPage").then((m) => ({
    default: m.SchoolDashboardPage,
  })),
);
const BureauDashboardPage = lazy(() =>
  import("@/components/bureau/BureauDashboardPage").then((m) => ({
    default: m.BureauDashboardPage,
  })),
);
const BureauCenterPage = lazy(() =>
  import("@/components/bureau/BureauCenterPage").then((m) => ({
    default: m.BureauCenterPage,
  })),
);
const TeacherManagePage = lazy(() =>
  import("@/components/school/TeacherManagePage").then((m) => ({
    default: m.TeacherManagePage,
  })),
);
const ExamManagePage = lazy(() =>
  import("@/components/school/ExamManagePage").then((m) => ({
    default: m.ExamManagePage,
  })),
);
const WarningPage = lazy(() =>
  import("@/components/school/WarningPage").then((m) => ({
    default: m.WarningPage,
  })),
);
/* 扫描计费统计（含 recharts，懒加载降低首屏体积） */
const ScanConsumptionPage = lazy(() =>
  import("@/components/scan-billing/ScanConsumptionPage").then((m) => ({
    default: m.ScanConsumptionPage,
  })),
);
const UsageSummaryPage = lazy(() =>
  import("@/components/scan-billing/UsageSummaryPage").then((m) => ({
    default: m.UsageSummaryPage,
  })),
);
/* 独立老师个人账本（口径 B，与 scan-billing 口径 A 物理分离、并列不合并） */
const PaymentWalletPage = lazy(() =>
  import("@/components/payment/PaymentWalletPage").then((m) => ({
    default: m.PaymentWalletPage,
  })),
);
const PaymentLedgerPage = lazy(() =>
  import("@/components/payment/PaymentLedgerPage").then((m) => ({
    default: m.PaymentLedgerPage,
  })),
);

/* ── Placeholder component for future pages ── */
function PlaceholderPage({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh]">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-primary" />
      </div>
      <h2 className="text-xl font-semibold text-foreground mb-2">{title}</h2>
      <p className="text-muted-foreground text-sm">{description}</p>
    </div>
  );
}

function NeedsClassPlaceholder() {
  const { t } = useLocale();
  return (
    <div className="flex flex-col items-center justify-center h-[60vh]">
      <Users2 className="w-16 h-16 text-muted-foreground/30 mb-4" />
      <h2 className="text-lg font-semibold text-foreground mb-1">
        {t("common.selectClassFirst")}
      </h2>
      <p className="text-muted-foreground text-sm">
        {t("common.selectClassHint")}
      </p>
    </div>
  );
}

/* ── 无权访问该功能域（独立老师深链越界时的中性态：明说 + 给回首页的出口，⛔ 不静默回落） ── */
function NavDeniedPlaceholder({ onBackHome }: { onBackHome: () => void }) {
  const { t } = useLocale();
  return (
    <div className="flex flex-col items-center justify-center h-[60vh]">
      <ShieldOff className="w-16 h-16 text-muted-foreground/30 mb-4" />
      <h2 className="text-lg font-semibold text-foreground mb-1">
        {t("account.accessDenied.title")}
      </h2>
      <p className="text-muted-foreground text-sm mb-5">
        {t("common.navDeniedDesc")}
      </p>
      <Button variant="outline" size="sm" onClick={onBackHome}>
        {t("auth.backToHome")}
      </Button>
    </div>
  );
}

/* ── 接入方式 / 零设备改造指引页（原「多端管理」占位） ── */
function AccessGuidePage({
  onPhotoClick,
  onNavChange,
}: {
  onPhotoClick: () => void;
  onNavChange: (id: string) => void;
}) {
  const { t } = useLocale();

  const methods = [
    {
      key: "photo",
      icon: Camera,
      title: t("settings.access.photo.title"),
      desc: t("settings.access.photo.desc"),
      onClick: onPhotoClick,
    },
    {
      key: "upload",
      icon: Upload,
      title: t("settings.access.upload.title"),
      desc: t("settings.access.upload.desc"),
      onClick: () => onNavChange("grading-start"),
    },
    {
      key: "scanner",
      icon: ScanLine,
      title: t("settings.access.scanner.title"),
      desc: t("settings.access.scanner.desc"),
      onClick: () => onNavChange("settings-hardware"),
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-lg font-semibold text-foreground">
          {t("settings.access.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("settings.access.subtitle")}
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {methods.map((m) => (
          <button
            key={m.key}
            onClick={m.onClick}
            className="flex flex-col items-start gap-3 p-5 rounded-xl bg-card border border-border/50 hover:border-primary/30 hover:shadow-md transition-all duration-200 hover-scale cursor-pointer text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <m.icon className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-medium text-foreground">{m.title}</h3>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                {m.desc}
              </p>
            </div>
            <span className="text-xs text-primary inline-flex items-center gap-1 mt-auto">
              {t("settings.access.enter")}
              <ArrowRight className="w-3 h-3" />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ── IDs that require a selected class ── */
const CLASS_REQUIRED_IDS = new Set([
  "class-dashboard",
  "class-students",
  "analytics-portrait",
  "analytics-compare",
  "analytics-questions",
  "class-knowledge",
  "ai-review",
  "ai-targeted",
  "ai-layered",
  "prep-lesson",
]);

/* ── 教育局模块：仅平台管理员可访问 ── */
const BUREAU_ADMIN_ONLY_IDS = new Set(["bureau-dashboard", "bureau-center"]);

/* ── 家长端：仅家长角色可访问 ── */
const PARENT_ONLY_IDS = new Set(["parent-wuyu"]);

/* ── nav id → 后端功能开关 key（E08 学校级 AI 管控，派生自 NAV_ITEMS.featureKey） ── */
const NAV_FEATURE_KEY: Record<string, string> = {};
NAV_ITEMS.forEach((group) => {
  group.children?.forEach((child) => {
    if (child.featureKey) NAV_FEATURE_KEY[child.id] = child.featureKey;
  });
});

export default function Index() {
  const { user } = useAuth();
  const { t } = useLocale();

  // E08 学校级 AI 管控：走后端 feature-flags，关闭后隐藏对应入口
  const { data: featureFlags } = useFeatureFlags();
  const aiChatEnabled = useIsFeatureEnabled("ai_chat");
  const disabledFeatureKeys = useMemo(() => {
    const set = new Set<string>();
    (featureFlags ?? []).forEach((f) => {
      if (!f.enabled) set.add(f.key);
    });
    return set;
  }, [featureFlags]);

  const {
    schoolLevel: selectedSchoolLevel,
    grade: selectedGrade,
    selectedClass,
    selectedSubject,
    setSchoolLevel,
    setGrade,
    setSelectedClass,
    setSelectedSubject,
  } = useGlobalFilters();

  // Active nav – URL 驱动（/nav/:navId），刷新后仍停留在原功能域
  const { navId } = useParams<{ navId?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const activeNavId = navId ?? "home";

  // localStorage 旧导航持久化 → URL 语义的一次性迁移
  const navMigrated = useRef(false);
  useEffect(() => {
    if (navMigrated.current) return;
    navMigrated.current = true;
    if (navId) return;
    try {
      const saved = localStorage.getItem(STORAGE_KEY_ACTIVE) || "home";
      const target =
        saved === "settings-account" || saved === "settings-subject"
          ? "settings-personal"
          : saved;
      if (target && target !== "home") {
        navigate(`/nav/${target}`, { replace: true });
      }
    } catch {
      // 隐私模式/存储不可用时静默跳过，默认落在首页
    }
  }, [navId, navigate]);

  // For cross-page student selection (e.g. portrait → student list)
  const [pendingStudent, setPendingStudent] = useState<string | undefined>();
  // For cross-page resource → exam navigation
  const [pendingResourceId, setPendingResourceId] = useState<
    string | undefined
  >();

  const handleNavChange = (id: string, tab?: string) => {
    // 仅 class-students 保留 pendingStudent；ai-targeted 统一走 navigateToTargeted 携带学生，
    // 走 onNavChange 的裸导航一律清空，避免残留上一次被点学生的旧值
    if (id !== "class-students") setPendingStudent(undefined);
    const query = tab ? `?tab=${encodeURIComponent(tab)}` : "";
    navigate(`/nav/${id}${query}`);
  };

  const navigateToStudent = (studentName: string) => {
    setPendingStudent(studentName);
    navigate("/nav/class-students");
  };

  const navigateToTargeted = (studentName: string) => {
    setPendingStudent(studentName);
    navigate("/nav/ai-targeted");
  };

  const navigateToExam = (resourceId?: string) => {
    // Always generate a unique key so ExamGenPage always re-triggers loading
    setPendingResourceId(`${resourceId || "nav"}__${Date.now()}`);
    navigate("/nav/prep-exam");
  };

  const navigateToGradingFolder = (folderName: string) => {
    navigate(`/nav/grading-start?folder=${encodeURIComponent(folderName)}`);
  };

  // Class & student management dialogs
  const [classDialogOpen, setClassDialogOpen] = useState(false);
  const [studentDialogOpen, setStudentDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [photoDialogOpen, setPhotoDialogOpen] = useState(false);
  const [managingClass, setManagingClass] = useState<ClassRecord | null>(null);

  const { data: classes = [] } = useClasses(selectedSchoolLevel, selectedGrade);
  const selectedClassInfo = classes.find((c) => c.id === selectedClass);

  const gradingRef = useRef<HTMLDivElement>(null);

  /* ── Content renderer ── */
  const renderContent = () => {
    // 深链闸：独立老师（仅任课教师账号）请求白名单外的功能域 ⇒ 明确拒绝渲染。
    // ⛔ 与侧栏共用同一份白名单（constants/systemRoles.ts），不另建第二份谓词。
    // 位置刻意在 CLASS_REQUIRED_IDS 之前：拒绝优先于「请先选班」，且不改后者语义。
    if (!isNavPageAllowed(user, activeNavId)) {
      return (
        <NavDeniedPlaceholder onBackHome={() => handleNavChange("home")} />
      );
    }

    // Pages that need a class selected
    if (CLASS_REQUIRED_IDS.has(activeNavId) && !selectedClass) {
      return <NeedsClassPlaceholder />;
    }

    // E08 学校级 AI 管控：带 featureKey 的入口被后端关闭时不可达
    const navFeatureKey = NAV_FEATURE_KEY[activeNavId];
    if (navFeatureKey && disabledFeatureKeys.has(navFeatureKey)) {
      return (
        <PlaceholderPage
          icon={ShieldOff}
          title={t("common.featureDisabled")}
          description={t("common.featureDisabledDesc")}
        />
      );
    }

    // 教育局模块：仅系统管理员/子系统管理员可见
    if (BUREAU_ADMIN_ONLY_IDS.has(activeNavId) && !isPlatformAdmin(user)) {
      return (
        <PlaceholderPage
          icon={ShieldOff}
          title={t("admin.denied")}
          description=""
        />
      );
    }

    // 家长端：仅家长角色可见
    if (PARENT_ONLY_IDS.has(activeNavId) && !isParent(user)) {
      return (
        <PlaceholderPage
          icon={ShieldOff}
          title={t("parent.denied")}
          description={t("parent.deniedDesc")}
        />
      );
    }

    switch (activeNavId) {
      /* ── 首页 ── */
      case "home":
        return (
          <div className="space-y-6" ref={gradingRef}>
            <GlobalSearchBar
              selectedClass={selectedClass}
              onNavChange={handleNavChange}
              onNavigateToStudent={navigateToStudent}
              onUploadClick={() => setUploadDialogOpen(true)}
            />
            <GradingEntrySection
              selectedSubject={selectedSubject}
              selectedClass={selectedClass}
              onPhotoClick={() => setPhotoDialogOpen(true)}
            />
            <StatsOverview
              selectedSubject={selectedSubject}
              selectedClass={selectedClass}
              onNavChange={handleNavChange}
            />
            <StudentMatrixPreview
              selectedSubject={selectedSubject}
              selectedClass={selectedClass}
              onNavChange={handleNavChange}
              onNavigateToTargeted={navigateToTargeted}
            />
            <TodoAndQuickActions
              selectedSubject={selectedSubject}
              selectedClass={selectedClass}
              onNavChange={handleNavChange}
              onScrollToGrading={() =>
                gradingRef.current?.scrollIntoView({ behavior: "smooth" })
              }
            />
          </div>
        );

      /* ── 新功能 ── */
      case "whats-new":
        return <NewFeaturesPage onNavChange={handleNavChange} />;

      /* ── 我的班级 ── */
      case "class-dashboard":
        return (
          <ClassDashboard
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            onNavChange={handleNavChange}
            onNavigateToStudent={navigateToStudent}
            onNavigateToTargeted={navigateToTargeted}
            classMeta={selectedClassInfo}
            initialTab={searchParams.get("tab") ?? undefined}
          />
        );
      case "class-students":
        return (
          <StudentPanoramaPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            onNavChange={handleNavChange}
            initialStudentName={pendingStudent}
            onNavigateToTargeted={navigateToTargeted}
          />
        );
      case "settings-class":
        return <ClassManagePage />;

      /* ── 学情分析 ── */
      case "analytics-grade":
        return (
          <GradeAnalysisPage
            selectedSubject={selectedSubject}
            schoolLevel={selectedSchoolLevel}
            selectedGrade={selectedGrade}
            onNavChange={handleNavChange}
          />
        );
      case "analytics-portrait":
        return (
          <ClassPortraitPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            onNavigateToStudent={navigateToStudent}
          />
        );
      case "analytics-compare":
        return (
          <CompareAnalysisPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            schoolLevel={selectedSchoolLevel}
            onNavChange={handleNavChange}
          />
        );
      case "analytics-questions":
        return (
          <QuestionAnalysisPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            schoolLevel={selectedSchoolLevel}
            onNavChange={handleNavChange}
            onNavigateToStudent={navigateToStudent}
          />
        );
      case "class-knowledge":
        return (
          <KnowledgeGraphPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            schoolLevel={selectedSchoolLevel}
            onNavChange={handleNavChange}
          />
        );

      /* ── AI精准教学 ── */
      case "ai-review":
        return (
          <ClassReviewPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            schoolLevel={selectedSchoolLevel}
            onNavChange={handleNavChange}
            onOpenSession={(classId, subject) => {
              setSelectedClass(classId);
              setSelectedSubject(subject);
            }}
          />
        );
      case "ai-targeted":
        return (
          <TargetedImprovePage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            onNavChange={handleNavChange}
            initialStudentName={pendingStudent}
            onNavigateToStudent={navigateToStudent}
          />
        );
      case "ai-layered":
        return (
          <LayeredPushPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass!}
            schoolLevel={selectedSchoolLevel}
            onNavChange={handleNavChange}
          />
        );

      /* ── AI备课 ── */
      case "prep-matrix":
        return <PrepMatrixPage />;
      case "prep-catalog":
        return <TextbookCatalogPage onNavChange={handleNavChange} />;
      case "prep-bank":
        return (
          <PrepPlanPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass || ""}
            onNavChange={handleNavChange}
          />
        );
      case "prep-lesson":
        return (
          <LessonPlanPage
            selectedSubject={selectedSubject}
            selectedGrade={selectedGrade}
            selectedClass={selectedClass || ""}
            selectedClassName={selectedClassInfo?.name || ""}
            onNavChange={handleNavChange}
          />
        );
      case "prep-compose":
        return (
          <SmartGenPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass || ""}
            onNavChange={handleNavChange}
          />
        );
      case "prep-exam":
        return (
          <ExamGenPage
            selectedSubject={selectedSubject}
            selectedClass={selectedClass || ""}
            selectedGrade={selectedGrade}
            selectedSchoolLevel={selectedSchoolLevel}
            onNavChange={handleNavChange}
            loadResourceId={pendingResourceId}
            onResourceLoaded={() => setPendingResourceId(undefined)}
          />
        );
      case "prep-video":
        return <ResourceLibPage />;
      case "prep-question-bank":
        return <QuestionBankPage />;
      case "canteen-ledger":
        return <CanteenLedgerPage />;

      /* ── 作业批改 ── */
      case "grading-start":
        return <GradingStartPage selectedClass={selectedClass || ""} />;
      case "grading-history":
        return (
          <GradingHistoryPage
            onOpenFolder={navigateToGradingFolder}
            onStartGrading={() => navigate("/nav/grading-start")}
          />
        );
      case "grading-errors":
        return <ErrorBookPage selectedClass={selectedClass || ""} />;
      case "flow-tasks":
        return <FlowTeacherTasksPage />;

      /* ── 学生成长 ── */
      case "wuyu-profile":
        return (
          <WuyuProfilePage
            selectedClass={selectedClass}
            selectedSubject={selectedSubject}
            onNavChange={handleNavChange}
          />
        );
      case "assessment":
        return (
          <AssessmentPage
            selectedClass={selectedClass}
            onNavChange={handleNavChange}
          />
        );
      /* ── 学校驾驶舱 ── */
      case "school-dashboard":
        // 驾驶舱内置「全校/各年级」选择器，默认全校概览，不受教学筛选污染
        return <SchoolDashboardPage />;

      /* ── 学校预警中心 ── */
      case "school-warning":
        return <WarningPage />;

      /* ── 教育局驾驶舱 ── */
      case "bureau-dashboard":
        return <BureauDashboardPage />;
      case "bureau-center":
        return <BureauCenterPage />;
      case "student-ops":
        return <StudentOpsPage />;
      case "parent-wuyu":
        return <ParentPortalPage />;

      /* ── 设置 ── */
      case "settings-personal":
        return <PersonalSettingsPage />;
      case "settings-subject":
        return (
          <SubjectConfigPage
            selectedSubject={selectedSubject}
            selectedSchoolLevel={selectedSchoolLevel}
            selectedGrade={selectedGrade}
            onSubjectChange={setSelectedSubject}
          />
        );
      case "settings-hardware":
        return <HardwareConfigPage />;
      case "settings-multi-device":
        return (
          <AccessGuidePage
            onPhotoClick={() => setPhotoDialogOpen(true)}
            onNavChange={handleNavChange}
          />
        );
      case "settings-preferences":
        return <SystemSettingsPage />;
      case "settings-teacher":
        return <TeacherManagePage />;
      case "settings-exam":
        return <ExamManagePage />;

      /* ── 系统运营 ── */
      case "scan-consumption":
        return <ScanConsumptionPage />;
      case "usage-summary":
        return <UsageSummaryPage />;

      /* ── 我的账户（口径 B · 个人账本） ── */
      case "payment-wallet":
        return <PaymentWalletPage />;
      case "payment-ledger":
        return <PaymentLedgerPage />;

      default:
        return (
          <PlaceholderPage
            icon={FileText}
            title={t("common.comingSoon")}
            description={t("common.comingSoonDesc")}
          />
        );
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* 侧边栏：固定高度，内部自己可以滚动 */}
      <Sidebar activeNavId={activeNavId} onNavChange={handleNavChange} />

      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        {/* 顶部导航：固定在顶部 */}
        <TopHeader
          selectedSchoolLevel={selectedSchoolLevel}
          selectedGrade={selectedGrade}
          selectedClass={selectedClass}
          selectedSubject={selectedSubject}
          onSchoolLevelChange={setSchoolLevel}
          onGradeChange={setGrade}
          onClassChange={setSelectedClass}
          onSubjectChange={setSelectedSubject}
          onManageClasses={() => setClassDialogOpen(true)}
          onNavChange={handleNavChange}
          showTeachingFilters={
            !(NO_TEACHING_FILTER_IDS as readonly string[]).includes(activeNavId)
          }
        />

        {/* 中间内容区域：唯一可以滑动的地方 */}
        <main className="flex-1 p-6 overflow-y-auto overflow-x-hidden relative">
          {/* 被深链闸拒的功能域不渲染面包屑（否则会把无权访问的页面名露出来） */}
          {isNavPageAllowed(user, activeNavId) && (
            <ContentBreadcrumb
              activeNavId={activeNavId}
              onNavChange={handleNavChange}
            />
          )}
          <Suspense
            fallback={
              <div className="flex h-[400px] flex-col items-center justify-center gap-3 text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin" />
                <p className="text-sm">{t("common.loading")}</p>
              </div>
            }
          >
            {renderContent()}
          </Suspense>
        </main>
      </div>

      <ClassManageDialog
        open={classDialogOpen}
        onOpenChange={setClassDialogOpen}
        schoolLevel={selectedSchoolLevel}
        grade={selectedGrade}
        onManageStudents={(cls) => {
          setManagingClass(cls);
          setStudentDialogOpen(true);
        }}
      />
      <StudentManageDialog
        open={studentDialogOpen}
        onOpenChange={setStudentDialogOpen}
        classInfo={managingClass}
      />

      {activeNavId === "home" && <OnboardingTour />}

      <ResourceUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onNavigateToExam={(resourceId) => {
          setUploadDialogOpen(false);
          navigateToExam(resourceId);
        }}
      />

      <PhotoGradingDialog
        open={photoDialogOpen}
        onOpenChange={setPhotoDialogOpen}
        selectedSubject={selectedSubject}
        selectedClass={selectedClass || ""}
        selectedSchoolLevel={selectedSchoolLevel}
        selectedGrade={selectedGrade}
      />

      {aiChatEnabled && (
        <FloatingChat activeNavId={activeNavId} onNavigate={handleNavChange} />
      )}
    </div>
  );
}
