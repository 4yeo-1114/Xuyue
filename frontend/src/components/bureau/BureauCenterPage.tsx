import { useMemo } from "react";
import { AlertTriangle, ClipboardList, CalendarDays } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLocale } from "@/contexts/LocaleContext";
import { useWarnings, useTickets } from "@/hooks/useBureau";
import { WarningList } from "@/components/bureau/WarningList";
import { TicketPanel } from "@/components/bureau/TicketPanel";

export function BureauCenterPage() {
  const { t } = useLocale();
  const { warnings } = useWarnings();
  const { tickets, createTicket, updateStatus } = useTickets();

  const stats = useMemo(() => {
    const red = warnings.filter((w) => w.level === "red").length;
    const yellow = warnings.filter((w) => w.level === "yellow").length;
    const pendingTickets = tickets.filter(
      (t) => t.status === "pending" || t.status === "in_progress",
    ).length;
    const thisMonth = new Date().getMonth() + 1;
    const thisYear = new Date().getFullYear();
    const monthNew = tickets.filter((t) => {
      const d = new Date(t.createdAt);
      return d.getMonth() + 1 === thisMonth && d.getFullYear() === thisYear;
    }).length;
    return { total: warnings.length, red, yellow, pendingTickets, monthNew };
  }, [warnings, tickets]);

  return (
    <div className="space-y-5">
      <Card className="border-border/70 bg-white shadow-sm">
        <CardContent className="flex items-center justify-between p-5">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className="border-blue-200 bg-blue-50 text-blue-600"
              >
                {t("bureau.center.badge")}
              </Badge>
              <span className="text-xs text-slate-400">
                {t("bureau.center.subtitle")}
              </span>
            </div>
            <h2 className="text-2xl font-semibold text-slate-900">
              {t("bureau.center.title")}
            </h2>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="warnings" className="w-full">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="warnings">
            {t("bureau.center.tab.warnings")}
          </TabsTrigger>
          <TabsTrigger value="tickets">
            {t("bureau.center.tab.tickets")}
          </TabsTrigger>
          <TabsTrigger value="analytics">
            {t("bureau.center.tab.analytics")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="warnings" className="mt-4">
          <WarningList warnings={warnings} />
        </TabsContent>

        <TabsContent value="tickets" className="mt-4">
          <TicketPanel
            tickets={tickets}
            onCreateTicket={createTicket}
            onUpdateStatus={updateStatus}
          />
        </TabsContent>

        <TabsContent value="analytics" className="mt-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="border-border/70 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-slate-500">
                  <AlertTriangle className="h-4 w-4" />
                  {t("bureau.center.stats.total")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold text-slate-900">
                  {stats.total}
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {t("bureau.center.stats.totalSub", {
                    red: stats.red,
                    yellow: stats.yellow,
                  })}
                </p>
              </CardContent>
            </Card>
            <Card className="border-border/70 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-slate-500">
                  <ClipboardList className="h-4 w-4" />
                  {t("bureau.center.stats.pending")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold text-slate-900">
                  {stats.pendingTickets}
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {t("bureau.center.stats.pendingSub")}
                </p>
              </CardContent>
            </Card>
            <Card className="border-border/70 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-slate-500">
                  <CalendarDays className="h-4 w-4" />
                  {t("bureau.center.stats.monthNew")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold text-slate-900">
                  {stats.monthNew}
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {t("bureau.center.stats.monthNewSub")}
                </p>
              </CardContent>
            </Card>
            <Card className="border-border/70 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-slate-500">
                  <AlertTriangle className="h-4 w-4" />
                  {t("bureau.center.stats.red")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold text-red-600">
                  {stats.red}
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {t("bureau.center.stats.redSub")}
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
