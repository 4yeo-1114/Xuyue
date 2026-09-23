import React, { useState, useEffect, useMemo } from "react";
import {
  format,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  isSameMonth,
  startOfWeek,
  endOfWeek,
  addMonths,
  subMonths,
  addWeeks,
  subWeeks,
  addDays,
  subDays,
  isToday,
} from "date-fns";
import { enUS, zhCN } from "date-fns/locale";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Plus,
  Trash2,
  Edit2,
  BookOpen,
  CheckCircle2,
  Circle,
  Loader2,
  Sparkles,
  Check,
  Clock,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  listPrepPlans,
  createPrepPlan,
  updatePrepPlan,
  deletePrepPlan as deletePrepPlanApi,
  PrepPlanRecord,
} from "@/services/api";

const SUBJECTS = ["全部", "语文", "数学", "英语", "科学"];
const SUBJECT_ALL = "全部";

const SUBJECT_COLORS: Record<string, string> = {
  语文: "bg-rose-100 text-rose-700 border-rose-200 hover:bg-rose-200",
  数学: "bg-blue-100 text-blue-700 border-blue-200 hover:bg-blue-200",
  英语: "bg-violet-100 text-violet-700 border-violet-200 hover:bg-violet-200",
  科学: "bg-emerald-100 text-emerald-700 border-emerald-200 hover:bg-emerald-200",
  物理: "bg-indigo-100 text-indigo-700 border-indigo-200 hover:bg-indigo-200",
  化学: "bg-cyan-100 text-cyan-700 border-cyan-200 hover:bg-cyan-200",
  生物: "bg-lime-100 text-lime-700 border-lime-200 hover:bg-lime-200",
  政治: "bg-orange-100 text-orange-700 border-orange-200 hover:bg-orange-200",
  历史: "bg-amber-100 text-amber-700 border-amber-200 hover:bg-amber-200",
  地理: "bg-sky-100 text-sky-700 border-sky-200 hover:bg-sky-200",
  默认: "bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200",
};

const getSubjectColor = (subject: string) =>
  SUBJECT_COLORS[subject] || SUBJECT_COLORS["默认"];

interface Props {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
}

export function PrepPlanPage({
  selectedSubject: _parentSubject,
  selectedClass,
  onNavChange,
}: Props) {
  const { t, locale } = useLocale();
  const dateLocale = locale === "en" ? enUS : zhCN;
  const [view, setView] = useState<"month" | "week" | "day">("month");
  const [currentDate, setCurrentDate] = useState(new Date());
  const [localSubject, setLocalSubject] = useState(SUBJECT_ALL);

  const weekDayLabels = useMemo(
    () =>
      Array.from({ length: 7 }, (_, i) =>
        t(`prepPlan.calendar.weekDay.${i + 1}`),
      ),
    [t],
  );

  const formatWeekDay = (index: number) =>
    `${t("prepPlan.calendar.weekDayPrefix")}${weekDayLabels[index]}`;

  const displaySubject = (subject: string) =>
    subject === SUBJECT_ALL
      ? t("prepPlan.calendar.subjectAll")
      : translateSubjectName(locale, subject);

  const [plans, setPlans] = useState<PrepPlanRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<PrepPlanRecord | null>(null);

  const [formData, setFormData] = useState({
    date: format(new Date(), "yyyy-MM-dd"),
    subject: "语文",
    content: "",
  });

  const fetchPlans = async () => {
    try {
      setLoading(true);
      // 获取前后几个月的计划数据
      const start = format(subMonths(currentDate, 2), "yyyy-MM-dd");
      const end = format(addMonths(currentDate, 2), "yyyy-MM-dd");
      const data = await listPrepPlans(start, end);
      setPlans(data);
    } catch (e: any) {
      toast.error(t("prepPlan.calendar.toast.loadFailed"), {
        description: e.message,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlans();
  }, [currentDate]);

  const handleSavePlan = async () => {
    if (!formData.content.trim())
      return toast.error(t("prepPlan.calendar.toast.contentRequired"));
    try {
      if (editingPlan) {
        const res = await updatePrepPlan(editingPlan.id, formData);
        setPlans(plans.map((p) => (p.id === editingPlan.id ? res : p)));
        toast.success(t("prepPlan.calendar.toast.updated"));
      } else {
        const res = await createPrepPlan(formData);
        setPlans([...plans, res]);
        toast.success(t("prepPlan.calendar.toast.added"));
      }
      setModalOpen(false);
    } catch (e: any) {
      toast.error(t("prepPlan.calendar.toast.saveFailed"), {
        description: e.message,
      });
    }
  };

  const toggleComplete = async (id: string, completed: boolean) => {
    try {
      // Optimistic update
      setPlans(plans.map((p) => (p.id === id ? { ...p, completed } : p)));
      await updatePrepPlan(id, { completed });
    } catch (e: any) {
      toast.error(t("prepPlan.calendar.toast.statusFailed"), {
        description: e.message,
      });
      setPlans(
        plans.map((p) => (p.id === id ? { ...p, completed: !completed } : p)),
      );
    }
  };

  const deletePlan = async (id: string) => {
    if (confirm(t("prepPlan.calendar.toast.deleteConfirm"))) {
      try {
        await deletePrepPlanApi(id);
        setPlans(plans.filter((p) => p.id !== id));
        toast.success(t("prepPlan.calendar.toast.deleted"));
      } catch (e: any) {
        toast.error(t("prepPlan.calendar.toast.deleteFailed"), {
          description: e.message,
        });
      }
    }
  };

  const openAddModal = (dateStr?: string) => {
    setEditingPlan(null);
    setFormData({
      date: dateStr || format(currentDate, "yyyy-MM-dd"),
      subject: localSubject === SUBJECT_ALL ? "语文" : localSubject,
      content: "",
    });
    setModalOpen(true);
  };

  const openEditModal = (plan: PrepPlanRecord) => {
    setEditingPlan(plan);
    setFormData({
      date: plan.date,
      subject: plan.subject,
      content: plan.content,
    });
    setModalOpen(true);
  };

  const handlePrev = () => {
    if (view === "month") setCurrentDate(subMonths(currentDate, 1));
    if (view === "week") setCurrentDate(subWeeks(currentDate, 1));
    if (view === "day") setCurrentDate(subDays(currentDate, 1));
  };

  const handleNext = () => {
    if (view === "month") setCurrentDate(addMonths(currentDate, 1));
    if (view === "week") setCurrentDate(addWeeks(currentDate, 1));
    if (view === "day") setCurrentDate(addDays(currentDate, 1));
  };

  const handleToday = () => setCurrentDate(new Date());

  const openDayView = (day: Date) => {
    setCurrentDate(day);
    setView("day");
  };

  const displayDateText = () => {
    if (view === "month")
      return format(currentDate, t("prepPlan.calendar.dateFormat.month"), {
        locale: dateLocale,
      });
    if (view === "week") {
      const start = startOfWeek(currentDate, { weekStartsOn: 1 });
      const end = endOfWeek(currentDate, { weekStartsOn: 1 });
      if (isSameMonth(start, end)) {
        return t("prepPlan.calendar.dateFormat.monthRangeSame", {
          start: format(
            start,
            locale === "en" ? "MMM d, yyyy" : "yyyy年 M月 d日",
            { locale: dateLocale },
          ),
          endDay: format(end, "d", { locale: dateLocale }),
        });
      }
      return t("prepPlan.calendar.dateFormat.monthRangeCross", {
        start: format(start, locale === "en" ? "MMM d" : "M月 d日", {
          locale: dateLocale,
        }),
        end: format(end, locale === "en" ? "MMM d" : "M月 d日", {
          locale: dateLocale,
        }),
      });
    }
    return format(currentDate, t("prepPlan.calendar.dateFormat.day"), {
      locale: dateLocale,
    });
  };

  const filteredPlans = plans.filter(
    (p) => localSubject === SUBJECT_ALL || p.subject === localSubject,
  );
  const getPlansForDate = (date: Date) => {
    const dateStr = format(date, "yyyy-MM-dd");
    return filteredPlans.filter((p) => p.date === dateStr);
  };

  // Month Calendar logic
  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(monthStart);
  const startDate = startOfWeek(monthStart, { weekStartsOn: 1 });
  const endDate = endOfWeek(monthEnd, { weekStartsOn: 1 });
  const monthDays = eachDayOfInterval({ start: startDate, end: endDate });

  // Week Calendar logic
  const weekStart = startOfWeek(currentDate, { weekStartsOn: 1 });
  const weekEnd = endOfWeek(currentDate, { weekStartsOn: 1 });
  const weekDays = eachDayOfInterval({ start: weekStart, end: weekEnd });

  return (
    <div className="flex flex-col h-full animate-fade-in duration-500 max-w-[1600px] mx-auto pb-8">
      {/* 沉浸式高级顶部栏 */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-8 mt-2 px-2">
        <div className="space-y-1.5">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-sm font-medium mb-2">
            <Sparkles className="w-4 h-4" />
            <span>{t("prepPlan.calendar.badge")}</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            {t("prepPlan.calendar.title")}
          </h1>
          <p className="text-muted-foreground text-sm max-w-xl">
            {t("prepPlan.calendar.subtitle")}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 bg-white p-2 rounded-2xl shadow-sm border border-border/60">
          <div className="flex items-center gap-2 px-2">
            <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">
              {t("prepPlan.calendar.subject")}
            </span>
            <Select value={localSubject} onValueChange={setLocalSubject}>
              <SelectTrigger className="w-[110px] h-9 border-none bg-muted/30 hover:bg-muted/50 transition-colors focus:ring-0 focus:ring-offset-0 rounded-xl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SUBJECTS.map((s) => (
                  <SelectItem key={s} value={s} className="rounded-lg">
                    {displaySubject(s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="w-px h-6 bg-border mx-1 hidden sm:block"></div>

          <Tabs
            value={view}
            onValueChange={(v) => setView(v as any)}
            className="w-auto"
          >
            <TabsList className="h-10 bg-muted/30 p-1 rounded-xl">
              <TabsTrigger
                value="month"
                className="rounded-lg px-4 data-[state=active]:shadow-sm"
              >
                {t("prepPlan.calendar.viewMonth")}
              </TabsTrigger>
              <TabsTrigger
                value="week"
                className="rounded-lg px-4 data-[state=active]:shadow-sm"
              >
                {t("prepPlan.calendar.viewWeek")}
              </TabsTrigger>
              <TabsTrigger
                value="day"
                className="rounded-lg px-4 data-[state=active]:shadow-sm"
              >
                {t("prepPlan.calendar.viewDay")}
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <Button
            onClick={() => openAddModal()}
            className="gap-1.5 h-10 rounded-xl px-5 shadow-sm hover:shadow transition-all ml-1"
          >
            <Plus className="w-4 h-4" /> {t("prepPlan.calendar.add")}
          </Button>
        </div>
      </div>

      {/* 悬浮日期导航条 */}
      <div className="flex items-center justify-between bg-white/80 backdrop-blur-md rounded-2xl border border-border/60 p-2.5 shadow-sm mb-6 sticky top-0 z-10 mx-2">
        <Button
          variant="outline"
          size="sm"
          onClick={handleToday}
          className="h-9 px-5 rounded-xl border-border/60 hover:bg-muted/50"
        >
          {t("prepPlan.calendar.backToToday")}
        </Button>
        <div className="flex items-center gap-2 sm:gap-6">
          <Button
            variant="ghost"
            size="icon"
            onClick={handlePrev}
            aria-label={t("prepPlan.calendar.prevPage")}
            className="h-9 w-9 rounded-xl hover:bg-muted/50"
          >
            <ChevronLeft className="w-5 h-5 text-muted-foreground" />
          </Button>
          <div className="flex flex-col items-center justify-center min-w-[160px]">
            <span className="text-lg font-bold tracking-tight text-foreground">
              {displayDateText()}
            </span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleNext}
            aria-label={t("prepPlan.calendar.nextPage")}
            className="h-9 w-9 rounded-xl hover:bg-muted/50"
          >
            <ChevronRight className="w-5 h-5 text-muted-foreground" />
          </Button>
        </div>
        <div className="w-[84px] hidden sm:block"></div> {/* 平衡布局 */}
      </div>

      {/* 视图内容区域 */}
      <div className="flex-1 min-h-[600px] px-2">
        {/* =======================
            高级月视图 (Month View) 
            ======================= */}
        {view === "month" && (
          <div className="rounded-3xl border border-border/60 bg-white text-card-foreground shadow-sm overflow-hidden flex flex-col h-full animate-in fade-in zoom-in-[0.98] duration-300">
            <div className="grid grid-cols-7 bg-slate-50/80 border-b border-border/60">
              {weekDayLabels.map((day, i) => (
                <div
                  key={day}
                  className={cn(
                    "py-4 text-center text-sm font-semibold text-slate-500",
                    (i === 5 || i === 6) && "text-rose-500/80",
                  )}
                >
                  {formatWeekDay(i)}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 flex-1 auto-rows-fr bg-border/40 gap-px">
              {monthDays.map((day, idx) => {
                const isCurrentMonth = isSameMonth(day, currentDate);
                const dayPlans = getPlansForDate(day);
                const today = isToday(day);
                return (
                  <div
                    key={day.toString()}
                    className={cn(
                      "bg-white min-h-[140px] p-2 transition-all duration-200 relative group cursor-pointer",
                      !isCurrentMonth && "bg-slate-50/50",
                      "hover:bg-slate-50 hover:shadow-inner z-0 hover:z-10",
                    )}
                    onClick={() => openDayView(day)}
                  >
                    <div className="flex items-center justify-between mb-2 px-1">
                      <button
                        type="button"
                        aria-label={t("prepPlan.calendar.openDay", {
                          date: format(day, "yyyy-MM-dd"),
                        })}
                        className={cn(
                          "text-sm font-bold w-8 h-8 flex items-center justify-center rounded-full transition-colors bg-transparent border-none cursor-pointer",
                          today
                            ? "bg-primary text-primary-foreground shadow-md shadow-primary/20"
                            : !isCurrentMonth
                              ? "text-muted-foreground/50"
                              : "text-slate-700",
                        )}
                        onClick={(e) => {
                          e.stopPropagation();
                          openDayView(day);
                        }}
                      >
                        {format(day, "d")}
                      </button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("prepPlan.calendar.add")}
                        className="h-7 w-7 rounded-full opacity-0 group-hover:opacity-100 bg-white/80 shadow-sm border border-border/50 text-primary hover:bg-primary hover:text-primary-foreground transition-all transform scale-90 group-hover:scale-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          openAddModal(format(day, "yyyy-MM-dd"));
                        }}
                      >
                        <Plus className="w-4 h-4" />
                      </Button>
                    </div>

                    <div className="space-y-1.5 px-1">
                      {dayPlans.slice(0, 3).map((p) => (
                        <div
                          key={p.id}
                          className={cn(
                            "text-xs px-2.5 py-1.5 rounded-lg border transition-all truncate",
                            p.completed
                              ? "bg-slate-100 text-slate-400 line-through border-transparent"
                              : getSubjectColor(p.subject),
                          )}
                        >
                          <span className="font-bold opacity-80 mr-1.5">
                            {translateSubjectName(locale, p.subject)}
                          </span>
                          {p.content}
                        </div>
                      ))}
                      {dayPlans.length > 3 && (
                        <div className="text-[11px] text-muted-foreground pl-1 mt-1 font-semibold flex items-center gap-1">
                          <div className="w-4 h-px bg-muted-foreground/30"></div>
                          {t("prepPlan.calendar.morePlans", {
                            count: dayPlans.length - 3,
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* =======================
            看板周视图 (Week View) 
            ======================= */}
        {view === "week" && (
          <div className="grid grid-cols-1 md:grid-cols-7 gap-4 h-full animate-in fade-in slide-in-from-bottom-4 duration-300">
            {weekDays.map((day, idx) => {
              const dayPlans = getPlansForDate(day);
              const today = isToday(day);
              return (
                <div
                  key={day.toString()}
                  className={cn(
                    "flex flex-col bg-white rounded-3xl border border-border/60 shadow-sm overflow-hidden transition-all",
                    today ? "ring-2 ring-primary/20 ring-offset-2" : "",
                  )}
                >
                  {/* Column Header */}
                  <div
                    className={cn(
                      "py-4 px-3 text-center border-b border-border/50 flex flex-col gap-1 items-center relative",
                      today ? "bg-primary/[0.03]" : "bg-slate-50/80",
                    )}
                  >
                    {today && (
                      <div className="absolute top-0 left-0 right-0 h-1 bg-primary"></div>
                    )}
                    <span
                      className={cn(
                        "text-xs font-semibold uppercase tracking-widest",
                        today ? "text-primary" : "text-slate-500",
                      )}
                    >
                      {formatWeekDay(idx)}
                    </span>
                    <span
                      className={cn(
                        "text-2xl font-black mt-0.5",
                        today ? "text-primary" : "text-slate-800",
                      )}
                    >
                      {format(day, "d")}
                    </span>
                  </div>

                  {/* Column Body */}
                  <div className="flex-1 p-3 bg-slate-50/30 space-y-3 overflow-y-auto">
                    {dayPlans.map((p) => (
                      <div
                        key={p.id}
                        className={cn(
                          "p-3 rounded-2xl border text-sm group relative transition-all duration-200 hover:shadow-md",
                          p.completed
                            ? "bg-slate-50/80 border-slate-200 text-slate-400"
                            : "bg-white border-slate-200 shadow-sm",
                        )}
                      >
                        <div className="flex flex-col gap-2.5">
                          <div className="flex items-center justify-between">
                            <span
                              className={cn(
                                "text-[11px] font-bold px-2 py-0.5 rounded-md border",
                                p.completed
                                  ? "bg-slate-200/50 text-slate-500 border-transparent"
                                  : getSubjectColor(p.subject),
                              )}
                            >
                              {translateSubjectName(locale, p.subject)}
                            </span>
                            <button
                              type="button"
                              aria-label={
                                p.completed
                                  ? t("prepPlan.calendar.markIncomplete")
                                  : t("prepPlan.calendar.markComplete")
                              }
                              className={cn(
                                "shrink-0 transition-all rounded-full p-0.5",
                                p.completed
                                  ? "text-primary hover:bg-primary/10"
                                  : "text-slate-300 hover:text-primary hover:bg-primary/5",
                              )}
                              onClick={() => toggleComplete(p.id, !p.completed)}
                            >
                              {p.completed ? (
                                <CheckCircle2 className="w-5 h-5" />
                              ) : (
                                <Circle className="w-5 h-5" />
                              )}
                            </button>
                          </div>

                          <div
                            className={cn(
                              "whitespace-pre-wrap break-words leading-relaxed text-[13px]",
                              p.completed && "line-through",
                            )}
                          >
                            {p.content}
                          </div>
                        </div>

                        {/* Hover Actions */}
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex bg-white/95 rounded-lg backdrop-blur-sm shadow-sm border border-slate-100 p-0.5">
                          <button
                            type="button"
                            aria-label={t("prepPlan.calendar.edit")}
                            className="p-1.5 text-slate-400 hover:text-primary rounded-md hover:bg-slate-50 transition-colors"
                            onClick={() => openEditModal(p)}
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            aria-label={t("prepPlan.calendar.delete")}
                            className="p-1.5 text-slate-400 hover:text-destructive rounded-md hover:bg-rose-50 transition-colors"
                            onClick={() => deletePlan(p.id)}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}

                    <Button
                      variant="ghost"
                      className="w-full h-10 text-xs text-slate-400 hover:text-primary hover:bg-primary/5 border border-dashed border-slate-300 bg-white rounded-2xl transition-all"
                      onClick={() => openAddModal(format(day, "yyyy-MM-dd"))}
                    >
                      <Plus className="w-4 h-4 mr-1.5" />{" "}
                      {t("prepPlan.calendar.addSchedule")}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* =======================
            沉浸日视图 (Day View) 
            ======================= */}
        {view === "day" && (
          <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-500">
            <div className="bg-white rounded-3xl border border-border/60 shadow-sm p-8 min-h-[600px] flex flex-col relative overflow-hidden">
              {/* Day Header Background Decoration */}
              <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none"></div>

              <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-10 relative z-10">
                <div className="flex items-center gap-4">
                  <div className="w-16 h-16 rounded-2xl bg-primary text-primary-foreground flex flex-col items-center justify-center shadow-lg shadow-primary/20">
                    <span className="text-sm font-medium opacity-80 leading-none">
                      {formatWeekDay(
                        currentDate.getDay() === 0
                          ? 6
                          : currentDate.getDay() - 1,
                      )}
                    </span>
                    <span className="text-2xl font-black leading-tight mt-0.5">
                      {format(currentDate, "d")}
                    </span>
                  </div>
                  <div>
                    <h2 className="text-3xl font-bold tracking-tight text-slate-800">
                      {format(
                        currentDate,
                        t("prepPlan.calendar.dateFormat.dayHeader"),
                        { locale: dateLocale },
                      )}
                    </h2>
                    <div className="text-muted-foreground flex items-center gap-2 mt-1.5 font-medium">
                      <Clock className="w-4 h-4" />
                      {isToday(currentDate)
                        ? t("prepPlan.calendar.today")
                        : t("prepPlan.calendar.thisDay")}
                      {t("prepPlan.calendar.dayPlanCount", {
                        count: getPlansForDate(currentDate).length,
                      })}
                    </div>
                  </div>
                </div>
                <Button
                  onClick={() =>
                    openAddModal(format(currentDate, "yyyy-MM-dd"))
                  }
                  className="rounded-xl h-11 px-6 shadow-md hover:shadow-lg transition-all"
                >
                  <Plus className="w-4 h-4 mr-2" />{" "}
                  {t("prepPlan.calendar.addNewPlan")}
                </Button>
              </div>

              <div className="flex-1 space-y-4 relative z-10">
                {getPlansForDate(currentDate).length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
                    <div className="w-24 h-24 rounded-full bg-slate-50 flex items-center justify-center mb-6 border border-slate-100 shadow-inner">
                      <BookOpen className="w-10 h-10 text-slate-300" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-700 mb-2">
                      {t("prepPlan.calendar.emptyTitle")}
                    </h3>
                    <p className="text-slate-500 max-w-sm mb-8">
                      {t("prepPlan.calendar.emptyDesc")}
                    </p>
                    <Button
                      variant="outline"
                      onClick={() =>
                        openAddModal(format(currentDate, "yyyy-MM-dd"))
                      }
                      className="rounded-xl px-8 h-11"
                    >
                      {t("prepPlan.calendar.planNow")}
                    </Button>
                  </div>
                ) : (
                  getPlansForDate(currentDate).map((p) => (
                    <div
                      key={p.id}
                      className={cn(
                        "flex items-start sm:items-center gap-5 p-5 rounded-2xl border transition-all duration-300 group",
                        p.completed
                          ? "bg-slate-50/50 border-slate-200"
                          : "bg-white shadow-sm border-slate-200 hover:border-primary/40 hover:shadow-md",
                      )}
                    >
                      <button
                        type="button"
                        aria-label={
                          p.completed
                            ? t("prepPlan.calendar.markIncomplete")
                            : t("prepPlan.calendar.markComplete")
                        }
                        className="shrink-0 flex items-center justify-center w-8 h-8 rounded-full transition-all mt-0.5 sm:mt-0"
                        onClick={() => toggleComplete(p.id, !p.completed)}
                      >
                        {p.completed ? (
                          <div className="bg-primary text-white rounded-full p-1 shadow-sm scale-110 transition-transform">
                            <Check className="w-5 h-5" />
                          </div>
                        ) : (
                          <div className="w-6 h-6 rounded-full border-2 border-slate-300 hover:border-primary transition-colors"></div>
                        )}
                      </button>

                      <div className="flex-1 min-w-0 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
                        <span
                          className={cn(
                            "text-sm font-bold px-3 py-1 rounded-lg border shrink-0 text-center w-20",
                            p.completed
                              ? "bg-slate-100 text-slate-400 border-transparent"
                              : getSubjectColor(p.subject),
                          )}
                        >
                          {translateSubjectName(locale, p.subject)}
                        </span>

                        <div
                          className={cn(
                            "text-[15px] whitespace-pre-wrap leading-relaxed flex-1",
                            p.completed
                              ? "text-slate-400 line-through"
                              : "text-slate-700 font-medium",
                          )}
                        >
                          {p.content}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("prepPlan.calendar.edit")}
                          className="h-9 w-9 rounded-xl text-slate-400 hover:text-primary hover:bg-primary/10"
                          onClick={() => openEditModal(p)}
                        >
                          <Edit2 className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("prepPlan.calendar.delete")}
                          className="h-9 w-9 rounded-xl text-slate-400 hover:text-destructive hover:bg-rose-50"
                          onClick={() => deletePlan(p.id)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 高级弹窗：Add / Edit Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-[480px] p-0 overflow-hidden border-none shadow-2xl rounded-3xl">
          <div className="bg-gradient-to-r from-primary/10 to-transparent p-6 pb-4">
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              {editingPlan ? (
                <Edit2 className="w-5 h-5 text-primary" />
              ) : (
                <Sparkles className="w-5 h-5 text-primary" />
              )}
              {editingPlan
                ? t("prepPlan.calendar.editPlan")
                : t("prepPlan.calendar.newPlan")}
            </DialogTitle>
            <DialogDescription className="mt-1.5 text-slate-600">
              {t("prepPlan.calendar.modalDesc")}
            </DialogDescription>
          </div>

          <div className="p-6 space-y-6 bg-white">
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-2.5">
                <Label className="text-slate-600 font-semibold">
                  {t("prepPlan.calendar.date")}
                </Label>
                <Input
                  type="date"
                  className="rounded-xl h-11 border-slate-200 shadow-sm focus-visible:ring-primary/20"
                  value={formData.date}
                  onChange={(e) =>
                    setFormData({ ...formData, date: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2.5">
                <Label className="text-slate-600 font-semibold">
                  {t("prepPlan.calendar.selectSubject")}
                </Label>
                <Select
                  value={formData.subject}
                  onValueChange={(v) =>
                    setFormData({ ...formData, subject: v })
                  }
                >
                  <SelectTrigger className="rounded-xl h-11 border-slate-200 shadow-sm focus:ring-primary/20">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="rounded-xl">
                    {SUBJECTS.filter((s) => s !== SUBJECT_ALL).map((s) => (
                      <SelectItem
                        key={s}
                        value={s}
                        className="rounded-lg my-0.5"
                      >
                        {translateSubjectName(locale, s)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2.5">
              <Label className="text-slate-600 font-semibold">
                {t("prepPlan.calendar.planContent")}
              </Label>
              <Textarea
                className="min-h-[140px] rounded-xl border-slate-200 shadow-sm focus-visible:ring-primary/20 resize-none p-4 text-base"
                placeholder={t("prepPlan.calendar.contentPlaceholder")}
                value={formData.content}
                onChange={(e) =>
                  setFormData({ ...formData, content: e.target.value })
                }
              />
            </div>
          </div>

          <div className="p-6 pt-0 bg-white flex justify-end gap-3">
            <Button
              variant="outline"
              className="rounded-xl px-6 h-11"
              onClick={() => setModalOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button
              className="rounded-xl px-8 h-11 shadow-md hover:shadow-lg transition-all"
              onClick={handleSavePlan}
            >
              {editingPlan
                ? t("prepPlan.calendar.saveChanges")
                : t("prepPlan.calendar.confirmAdd")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
