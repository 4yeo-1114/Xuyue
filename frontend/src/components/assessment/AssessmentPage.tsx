import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ClipboardList, ClipboardCheck, Tags, ShieldCheck, TrendingUp } from "lucide-react";
import { AssessmentDefinitionsTab } from "./AssessmentDefinitionsTab";
import { AssessmentSessionsTab } from "./AssessmentSessionsTab";
import { AssessmentResultsTab } from "./AssessmentResultsTab";
import { AssessmentConsentTab } from "./AssessmentConsentTab";
import { DiagnosisTrendTab } from "./DiagnosisTrendTab";

interface AssessmentPageProps {
  /** 由 Index.tsx 传入；为空时自动回退到全局筛选的 selectedClass */
  selectedClass?: string;
  onNavChange?: (id: string) => void;
}

export function AssessmentPage({ selectedClass: selectedClassProp, onNavChange }: AssessmentPageProps) {
  const { t } = useLocale();
  const { selectedClass: filterClass } = useGlobalFilters();
  const selectedClass = selectedClassProp || filterClass;
  const [activeTab, setActiveTab] = useState("definitions");

  return (
    <div className="space-y-4 animate-fade-in">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t("assessment.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("assessment.subtitle")}</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full max-w-xl grid-cols-5">
          <TabsTrigger value="definitions" className="gap-1.5">
            <ClipboardList className="w-4 h-4" />
            {t("assessment.tab.definitions")}
          </TabsTrigger>
          <TabsTrigger value="sessions" className="gap-1.5">
            <ClipboardCheck className="w-4 h-4" />
            {t("assessment.tab.sessions")}
          </TabsTrigger>
          <TabsTrigger value="results" className="gap-1.5">
            <Tags className="w-4 h-4" />
            {t("assessment.tab.results")}
          </TabsTrigger>
          <TabsTrigger value="diagnosis" className="gap-1.5">
            <TrendingUp className="w-4 h-4" />
            {t("assessment.tab.diagnosis")}
          </TabsTrigger>
          <TabsTrigger value="consent" className="gap-1.5">
            <ShieldCheck className="w-4 h-4" />
            {t("assessment.tab.consent")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="definitions" className="mt-4">
          <AssessmentDefinitionsTab />
        </TabsContent>
        <TabsContent value="sessions" className="mt-4">
          <AssessmentSessionsTab selectedClass={selectedClass} />
        </TabsContent>
        <TabsContent value="results" className="mt-4">
          <AssessmentResultsTab selectedClass={selectedClass} />
        </TabsContent>
        <TabsContent value="diagnosis" className="mt-4">
          <DiagnosisTrendTab selectedClass={selectedClass} />
        </TabsContent>
        <TabsContent value="consent" className="mt-4">
          <AssessmentConsentTab selectedClass={selectedClass} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default AssessmentPage;
