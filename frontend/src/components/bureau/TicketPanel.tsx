import { useState } from "react";
import { Plus, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import type { TaskTicket, WarningLevel, TicketStatus } from "@/types/bureau";

interface TicketPanelProps {
  tickets: TaskTicket[];
  onCreateTicket: (ticket: Omit<TaskTicket, "id" | "createdAt">) => void;
  onUpdateStatus: (id: string, status: TicketStatus) => void;
}

const statusLabelKey: Record<TicketStatus, string> = {
  pending: "bureau.ticket.status.pending",
  in_progress: "bureau.ticket.status.in_progress",
  resolved: "bureau.ticket.status.resolved",
  closed: "bureau.ticket.status.closed",
};
const statusColor: Record<TicketStatus, string> = {
  pending: "bg-slate-100 text-slate-700 border-slate-200",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  resolved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  closed: "bg-slate-100 text-slate-400 border-slate-200",
};
const statusProgress: Record<TicketStatus, number> = {
  pending: 25,
  in_progress: 50,
  resolved: 75,
  closed: 100,
};
const statusNext: Record<TicketStatus, TicketStatus | null> = {
  pending: "in_progress",
  in_progress: "resolved",
  resolved: "closed",
  closed: null,
};

const defaultForm = {
  title: "",
  description: "",
  targetSchool: "",
  targetPerson: "",
  deadline: "",
  level: "yellow" as WarningLevel,
  status: "pending" as TicketStatus,
};

export function TicketPanel({
  tickets,
  onCreateTicket,
  onUpdateStatus,
}: TicketPanelProps) {
  const { t } = useLocale();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(defaultForm);

  const handleSubmit = () => {
    if (
      !form.title ||
      !form.targetSchool ||
      !form.targetPerson ||
      !form.deadline
    )
      return;
    onCreateTicket({ ...form, createdBy: t("bureau.ticket.createdBy") });
    setForm(defaultForm);
    setShowForm(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-600">
          {t("bureau.ticket.count", { count: tickets.length })}
        </h3>
        <Button size="sm" onClick={() => setShowForm(!showForm)}>
          <Plus className="mr-1 h-4 w-4" />
          {showForm ? t("bureau.ticket.collapse") : t("bureau.ticket.create")}
        </Button>
      </div>

      {showForm && (
        <Card className="border-blue-200 bg-blue-50/40">
          <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
            <Input
              placeholder={t("bureau.ticket.form.title")}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
            <Select
              value={form.level}
              onValueChange={(v) =>
                setForm({ ...form, level: v as WarningLevel })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t("bureau.ticket.form.level")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="red">
                  {t("bureau.ticket.form.level.red")}
                </SelectItem>
                <SelectItem value="yellow">
                  {t("bureau.ticket.form.level.yellow")}
                </SelectItem>
                <SelectItem value="green">
                  {t("bureau.ticket.form.level.green")}
                </SelectItem>
              </SelectContent>
            </Select>
            <Textarea
              placeholder={t("bureau.ticket.form.desc")}
              className="sm:col-span-2"
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
            />
            <Input
              placeholder={t("bureau.ticket.form.school")}
              value={form.targetSchool}
              onChange={(e) =>
                setForm({ ...form, targetSchool: e.target.value })
              }
            />
            <Input
              placeholder={t("bureau.ticket.form.person")}
              value={form.targetPerson}
              onChange={(e) =>
                setForm({ ...form, targetPerson: e.target.value })
              }
            />
            <Input
              type="date"
              value={form.deadline}
              onChange={(e) => setForm({ ...form, deadline: e.target.value })}
            />
            <Button className="sm:col-span-2" onClick={handleSubmit}>
              {t("bureau.ticket.form.submit")}
            </Button>
          </CardContent>
        </Card>
      )}

      {tickets.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-sm text-slate-400">
          {t("bureau.ticket.empty")}
        </div>
      ) : (
        <div className="space-y-3">
          {tickets.map((ticket) => (
            <Card key={ticket.id} className="border-border/70 shadow-sm">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-slate-800">
                        {ticket.title}
                      </span>
                      <Badge
                        variant="outline"
                        className={cn("text-xs", statusColor[ticket.status])}
                      >
                        {t(statusLabelKey[ticket.status])}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-xs",
                          ticket.level === "red"
                            ? "border-red-200 bg-red-50 text-red-700"
                            : ticket.level === "yellow"
                              ? "border-amber-200 bg-amber-50 text-amber-700"
                              : "border-emerald-200 bg-emerald-50 text-emerald-700",
                        )}
                      >
                        {ticket.level === "red"
                          ? t("bureau.ticket.level.red")
                          : ticket.level === "yellow"
                            ? t("bureau.ticket.level.yellow")
                            : t("bureau.ticket.level.green")}
                      </Badge>
                    </div>
                    <p className="text-xs text-slate-500 line-clamp-2">
                      {ticket.description}
                    </p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                      <span>
                        {t("bureau.ticket.field.school", {
                          school: ticket.targetSchool,
                        })}
                      </span>
                      <span>
                        {t("bureau.ticket.field.person", {
                          person: ticket.targetPerson,
                        })}
                      </span>
                      <span>
                        {t("bureau.ticket.field.deadline", {
                          deadline: ticket.deadline,
                        })}
                      </span>
                    </div>
                    <Progress
                      value={statusProgress[ticket.status]}
                      className="h-1.5 w-40"
                    />
                  </div>
                  {statusNext[ticket.status] && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0"
                      onClick={() =>
                        onUpdateStatus(ticket.id, statusNext[ticket.status]!)
                      }
                    >
                      {t(statusLabelKey[statusNext[ticket.status]!])}{" "}
                      <ChevronRight className="ml-1 h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
