import { useState } from "react";
import { Users } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ClassSelector } from "@/components/student-ops/shared/ClassSelector";
import { ClubsTab } from "./ClubsTab";
import { BorrowsTab } from "./BorrowsTab";
import { ReadingTab } from "./ReadingTab";
import { HealthTab } from "./HealthTab";
import { LeaveManageTab } from "./LeaveTab";
import { AttendanceStatTab } from "./AttendanceStatTab";

interface CampusSectionProps {
  classId: string;
  onClassChange: (id: string) => void;
}

export function CampusSection({ classId, onClassChange }: CampusSectionProps) {
  const { t } = useLocale();
  const [tab, setTab] = useState("clubs");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <Users className="h-4 w-4 text-primary" />
          </div>
          <ClassSelector value={classId} onChange={onClassChange} />
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="clubs">
            {t("studentOps.campus.clubs")}
          </TabsTrigger>
          <TabsTrigger value="borrows">
            {t("studentOps.campus.bookBorrows")}
          </TabsTrigger>
          <TabsTrigger value="reading">
            {t("studentOps.campus.readingRecords")}
          </TabsTrigger>
          <TabsTrigger value="health">
            {t("studentOps.campus.healthChecks")}
          </TabsTrigger>
          <TabsTrigger value="leave">
            {t("studentOps.campus.leaveManage")}
          </TabsTrigger>
          <TabsTrigger value="attendance-stat">
            {t("studentOps.campus.attendanceStats")}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="clubs">
          <ClubsTab classId={classId} />
        </TabsContent>
        <TabsContent value="borrows">
          <BorrowsTab classId={classId} />
        </TabsContent>
        <TabsContent value="reading">
          <ReadingTab classId={classId} />
        </TabsContent>
        <TabsContent value="health">
          <HealthTab classId={classId} />
        </TabsContent>
        <TabsContent value="leave">
          <LeaveManageTab classId={classId} />
        </TabsContent>
        <TabsContent value="attendance-stat">
          <AttendanceStatTab classId={classId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
