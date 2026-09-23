import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { BadgeSection } from "@/components/student-ops/badges/BadgeSection";
import { CreditSection } from "@/components/student-ops/credits/CreditSection";
import { RewardSection } from "@/components/student-ops/rewards/RewardSection";
import { PracticeSection } from "@/components/student-ops/practice/PracticeSection";
import { CampusSection } from "@/components/student-ops/campus/CampusSection";

/**
 * 学生端运营域（C 域）主页面
 * 内部 Tab 覆盖：争章颁章 / 学分银行 / 兑换管理 / 校外实践 / 校园生活
 * 通过 useGlobalFilters() 读取/联动全局班级选择。
 */
export function StudentOpsPage() {
  const { t } = useLocale();
  const { selectedClass, setSelectedClass } = useGlobalFilters();
  const [tab, setTab] = useState("badges");

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{t("studentOps.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("studentOps.subtitle")}</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="badges">{t("studentOps.tabs.badges")}</TabsTrigger>
          <TabsTrigger value="credits">{t("studentOps.tabs.credits")}</TabsTrigger>
          <TabsTrigger value="rewards">{t("studentOps.tabs.rewards")}</TabsTrigger>
          <TabsTrigger value="practice">{t("studentOps.tabs.practice")}</TabsTrigger>
          <TabsTrigger value="campus">{t("studentOps.tabs.campus")}</TabsTrigger>
        </TabsList>

        <TabsContent value="badges" className="mt-4">
          <BadgeSection classId={selectedClass} onClassChange={setSelectedClass} />
        </TabsContent>
        <TabsContent value="credits" className="mt-4">
          <CreditSection classId={selectedClass} onClassChange={setSelectedClass} />
        </TabsContent>
        <TabsContent value="rewards" className="mt-4">
          <RewardSection classId={selectedClass} onClassChange={setSelectedClass} />
        </TabsContent>
        <TabsContent value="practice" className="mt-4">
          <PracticeSection classId={selectedClass} onClassChange={setSelectedClass} />
        </TabsContent>
        <TabsContent value="campus" className="mt-4">
          <CampusSection classId={selectedClass} onClassChange={setSelectedClass} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default StudentOpsPage;
