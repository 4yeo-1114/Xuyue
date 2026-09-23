import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Utensils, Save, Loader2 } from "lucide-react";
import {
  createCanteenRecord,
  listCanteenRecords,
  type CanteenRecordItem,
  type CanteenRecordPayload,
  type CanteenRecordType,
} from "@/services/api";

/** 今天日期（YYYY-MM-DD，作为表单 date 默认值） */
function todayISO(): string {
  const d = new Date();
  const mm = `${d.getMonth() + 1}`.padStart(2, "0");
  const dd = `${d.getDate()}`.padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** ISO 时间 → 本地可读时间（列表「记录时间」列） */
function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = `${d.getMonth() + 1}`.padStart(2, "0");
  const dd = `${d.getDate()}`.padStart(2, "0");
  const hh = `${d.getHours()}`.padStart(2, "0");
  const mi = `${d.getMinutes()}`.padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd} ${hh}:${mi}`;
}

/** 列表摘要：把各类型的核心字段拼成一行描述 */
function recordSummary(item: CanteenRecordItem): string {
  switch (item.type) {
    case "health_check":
      return [
        item.staff_name,
        item.temperature != null ? `${item.temperature}℃` : null,
        item.health_status,
      ]
        .filter(Boolean)
        .join(" · ");
    case "sample":
      return [item.meal_type, item.dish_name, item.review_result]
        .filter(Boolean)
        .join(" · ");
    case "accompany":
      return [item.meal_type, item.person_name, item.person_role]
        .filter(Boolean)
        .join(" · ");
    case "disinfection":
      return [item.area, item.method, item.operator_name]
        .filter(Boolean)
        .join(" · ");
    case "menu":
      return [item.meal_type, item.dishes].filter(Boolean).join(" · ");
    default:
      return "";
  }
}

/** 顶部 Tab 定义（顺序即展示顺序） */
const TABS: { type: CanteenRecordType; labelKey: string }[] = [
  { type: "health_check", labelKey: "canteen.tab.healthCheck" },
  { type: "sample", labelKey: "canteen.tab.sample" },
  { type: "accompany", labelKey: "canteen.tab.accompany" },
  { type: "disinfection", labelKey: "canteen.tab.disinfection" },
  { type: "menu", labelKey: "canteen.tab.menu" },
];

const MEAL_OPTIONS = [
  { value: "早餐", labelKey: "canteen.meal.breakfast" },
  { value: "午餐", labelKey: "canteen.meal.lunch" },
  { value: "晚餐", labelKey: "canteen.meal.dinner" },
];

const ROLE_OPTIONS = [
  { value: "校长", labelKey: "canteen.role.principal" },
  { value: "班主任", labelKey: "canteen.role.headTeacher" },
  { value: "教师", labelKey: "canteen.role.teacher" },
  { value: "家长", labelKey: "canteen.role.parent" },
  { value: "值日教师", labelKey: "canteen.role.duty" },
];

interface CanteenField {
  key: string;
  labelKey: string;
  /** 输入控件类型；select/bool 走下拉，textarea 走多行，其余走 Input */
  type?: "text" | "date" | "number" | "select" | "textarea" | "bool";
  options?: { value: string; labelKey: string }[];
  required?: boolean;
  full?: boolean;
}

/** 各类型的录入字段（宽松 schema，后端按 type 校验必填） */
const FIELDS_BY_TYPE: Record<CanteenRecordType, CanteenField[]> = {
  health_check: [
    {
      key: "date",
      labelKey: "canteen.field.date",
      type: "date",
      required: true,
    },
    { key: "staff_name", labelKey: "canteen.field.staffName", required: true },
    {
      key: "temperature",
      labelKey: "canteen.field.temperature",
      type: "number",
    },
    {
      key: "health_status",
      labelKey: "canteen.field.healthStatus",
      type: "select",
      options: [
        { value: "健康", labelKey: "canteen.health.ok" },
        { value: "一般", labelKey: "canteen.health.fair" },
        { value: "异常", labelKey: "canteen.health.bad" },
      ],
    },
    {
      key: "pass",
      labelKey: "canteen.field.pass",
      type: "bool",
      options: [
        { value: "true", labelKey: "canteen.bool.yes" },
        { value: "false", labelKey: "canteen.bool.no" },
      ],
    },
  ],
  sample: [
    {
      key: "date",
      labelKey: "canteen.field.date",
      type: "date",
      required: true,
    },
    {
      key: "meal_type",
      labelKey: "canteen.field.mealType",
      type: "select",
      options: MEAL_OPTIONS,
      required: true,
    },
    { key: "dish_name", labelKey: "canteen.field.dishName", required: true },
    { key: "sample_qty", labelKey: "canteen.field.sampleQty", type: "number" },
    { key: "sampler_name", labelKey: "canteen.field.samplerName" },
    {
      key: "storage_temp",
      labelKey: "canteen.field.storageTemp",
      type: "number",
    },
    {
      key: "review_result",
      labelKey: "canteen.field.reviewResult",
      type: "select",
      options: [
        { value: "合格", labelKey: "canteen.review.pass" },
        { value: "不合格", labelKey: "canteen.review.fail" },
      ],
    },
  ],
  accompany: [
    {
      key: "date",
      labelKey: "canteen.field.date",
      type: "date",
      required: true,
    },
    {
      key: "meal_type",
      labelKey: "canteen.field.mealType",
      type: "select",
      options: MEAL_OPTIONS,
      required: true,
    },
    {
      key: "person_name",
      labelKey: "canteen.field.personName",
      required: true,
    },
    {
      key: "person_role",
      labelKey: "canteen.field.personRole",
      type: "select",
      options: ROLE_OPTIONS,
    },
    {
      key: "comments",
      labelKey: "canteen.field.comments",
      type: "textarea",
      full: true,
    },
  ],
  disinfection: [
    {
      key: "date",
      labelKey: "canteen.field.date",
      type: "date",
      required: true,
    },
    { key: "area", labelKey: "canteen.field.area", required: true },
    { key: "method", labelKey: "canteen.field.method" },
    { key: "operator_name", labelKey: "canteen.field.operatorName" },
    {
      key: "result",
      labelKey: "canteen.field.result",
      type: "select",
      options: [
        { value: "已完成", labelKey: "canteen.done.yes" },
        { value: "未完成", labelKey: "canteen.done.no" },
      ],
    },
  ],
  menu: [
    {
      key: "date",
      labelKey: "canteen.field.date",
      type: "date",
      required: true,
    },
    {
      key: "meal_type",
      labelKey: "canteen.field.mealType",
      type: "select",
      options: MEAL_OPTIONS,
      required: true,
    },
    {
      key: "dishes",
      labelKey: "canteen.field.dishes",
      type: "textarea",
      required: true,
      full: true,
    },
    {
      key: "nutrition_note",
      labelKey: "canteen.field.nutritionNote",
      type: "textarea",
      full: true,
    },
  ],
};

/** 各类型表单默认值（下拉必有值，避免受控/非受控切换） */
const TYPE_DEFAULTS: Record<CanteenRecordType, Record<string, string>> = {
  health_check: { date: todayISO(), health_status: "健康", pass: "true" },
  sample: { date: todayISO(), meal_type: "午餐", review_result: "合格" },
  accompany: { date: todayISO(), meal_type: "午餐" },
  disinfection: { date: todayISO(), result: "已完成" },
  menu: { date: todayISO(), meal_type: "午餐" },
};

export function CanteenLedgerPage() {
  const { t } = useLocale();
  const [activeType, setActiveType] =
    useState<CanteenRecordType>("health_check");
  const [form, setForm] = useState<Record<string, string>>(
    () => TYPE_DEFAULTS.health_check,
  );
  const [submitting, setSubmitting] = useState(false);
  const [records, setRecords] = useState<CanteenRecordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(false);

  const setField = useCallback((key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  const loadRecords = useCallback(async () => {
    setLoadingList(true);
    try {
      const data = await listCanteenRecords({
        type: activeType,
        page: 1,
        page_size: 10,
      });
      setRecords(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      toast.error(t("canteen.toast.listFailed"));
    } finally {
      setLoadingList(false);
    }
  }, [activeType, t]);

  // 切换类型：重置表单 + 拉取该类型最近记录
  useEffect(() => {
    setForm({ ...TYPE_DEFAULTS[activeType] });
    loadRecords();
  }, [activeType, loadRecords]);

  const requiredFields = useMemo(
    () =>
      FIELDS_BY_TYPE[activeType].filter((f) => f.required).map((f) => f.key),
    [activeType],
  );

  const buildPayload = (): CanteenRecordPayload => {
    const payload: Record<string, unknown> = {
      type: activeType,
      date: form.date || todayISO(),
    };
    for (const f of FIELDS_BY_TYPE[activeType]) {
      const raw = form[f.key];
      if (raw === undefined || raw === "") continue;
      payload[f.key] =
        f.type === "number"
          ? Number(raw)
          : f.type === "bool"
            ? raw === "true"
            : raw;
    }
    return payload as unknown as CanteenRecordPayload;
  };

  const handleSubmit = async () => {
    for (const key of requiredFields) {
      const raw = form[key];
      if (!raw || !String(raw).trim()) {
        toast.error(
          t("canteen.toast.required", { field: t(`canteen.field.${key}`) }),
        );
        return;
      }
    }
    setSubmitting(true);
    try {
      await createCanteenRecord(buildPayload());
      toast.success(t("canteen.toast.created"));
      setForm({ ...TYPE_DEFAULTS[activeType] });
      loadRecords();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      toast.error(msg || t("canteen.toast.createFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="outline" className="gap-1">
            <Utensils className="w-3 h-3" />
            {t("canteen.badge")}
          </Badge>
        </div>
        <h2 className="text-lg font-semibold text-foreground">
          {t("canteen.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("canteen.subtitle")}
        </p>
      </div>

      {/* 类型 Tab */}
      <div className="flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.type}
            type="button"
            onClick={() => setActiveType(tab.type)}
            className={cn(
              "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              activeType === tab.type
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {/* 录入表单 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("canteen.formTitle")}</CardTitle>
          <CardDescription className="text-xs">
            {t("canteen.formDesc")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            {FIELDS_BY_TYPE[activeType].map((f) => (
              <div key={f.key} className={cn(f.full && "sm:col-span-2")}>
                <Label className="mb-1.5 block">
                  {t(f.labelKey)}
                  {f.required && (
                    <span className="text-destructive ml-0.5">*</span>
                  )}
                </Label>
                {f.type === "select" || f.type === "bool" ? (
                  <Select
                    value={form[f.key] || ""}
                    onValueChange={(v) => setField(f.key, v)}
                  >
                    <SelectTrigger>
                      <SelectValue
                        placeholder={t("canteen.selectPlaceholder")}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {f.options!.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {t(opt.labelKey)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : f.type === "textarea" ? (
                  <Textarea
                    value={form[f.key] || ""}
                    onChange={(e) => setField(f.key, e.target.value)}
                    rows={2}
                  />
                ) : (
                  <Input
                    type={
                      f.type === "number"
                        ? "number"
                        : f.type === "date"
                          ? "date"
                          : "text"
                    }
                    step={f.type === "number" ? "any" : undefined}
                    value={form[f.key] || ""}
                    onChange={(e) => setField(f.key, e.target.value)}
                  />
                )}
              </div>
            ))}
          </div>
          <Button onClick={handleSubmit} disabled={submitting} className="mt-5">
            {submitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {t("canteen.submit")}
          </Button>
        </CardContent>
      </Card>

      {/* 最近记录列表 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t("canteen.recent")}</CardTitle>
          <CardDescription className="text-xs">
            {t("canteen.recentDesc", { total })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadingList ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : records.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-8">
              {t("canteen.empty")}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="whitespace-nowrap">
                      {t("canteen.list.date")}
                    </TableHead>
                    <TableHead>{t("canteen.list.summary")}</TableHead>
                    <TableHead className="whitespace-nowrap">
                      {t("canteen.list.time")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {records.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="whitespace-nowrap">
                        {item.date}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {recordSummary(item) || "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-muted-foreground">
                        {formatTime(item.occurred_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
