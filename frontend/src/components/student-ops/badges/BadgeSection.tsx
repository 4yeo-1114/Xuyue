import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Medal,
  Plus,
  Loader2,
  Pencil,
  Ban,
  Award,
  RotateCcw,
  Users,
} from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  listBadgeDefinitions,
  createBadgeDefinition,
  updateBadgeDefinition,
  deleteBadgeDefinition,
  awardBadges,
  listBadgeAwards,
  revokeBadgeAward,
  type BadgeDefinition,
  type BadgeDefinitionInput,
} from "@/services/studentOpsApi";
import { ClassSelector } from "@/components/student-ops/shared/ClassSelector";
import { StudentMultiPicker } from "@/components/student-ops/shared/StudentMultiPicker";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";

const CATEGORIES = [
  "moral",
  "intellectual",
  "physical",
  "aesthetic",
  "labor",
  "ai_literacy",
];
const TYPES = ["red_scarf", "school_based"];

/** 五育维度分类 → i18n key 后缀（snake_case → PascalCase，如 ai_literacy → AiLiteracy） */
const badgeCategoryKey = (c: string) =>
  `studentOps.badges.category${c
    .split("_")
    .map((p) => (p ? p[0].toUpperCase() + p.slice(1) : ""))
    .join("")}`;

interface BadgeSectionProps {
  classId: string;
  onClassChange: (id: string) => void;
}

export function BadgeSection({ classId, onClassChange }: BadgeSectionProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("definitions");

  // 定义列表筛选
  const [category, setCategory] = useState<string>("");
  const [badgeType, setBadgeType] = useState<string>("");
  const [defPage, setDefPage] = useState(1);

  // 颁章记录筛选
  const [awardPage, setAwardPage] = useState(1);

  // 弹窗状态
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<BadgeDefinition | null>(null);
  const [awardOpen, setAwardOpen] = useState(false);
  const [awardBadgeId, setAwardBadgeId] = useState<string>("");

  // 业务确认弹窗（替代原生 window.confirm，保持全站 AlertDialog 一致）
  const [deactivateTarget, setDeactivateTarget] =
    useState<BadgeDefinition | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);

  const defQuery = useQuery({
    queryKey: ["so-badge-defs", category, badgeType, defPage],
    queryFn: () =>
      listBadgeDefinitions({
        category: category || undefined,
        badgeType: badgeType || undefined,
        page: defPage,
        pageSize: 20,
      }),
  });

  const awardQuery = useQuery({
    queryKey: ["so-badge-awards", classId, awardPage],
    queryFn: () =>
      listBadgeAwards({
        classId: classId || undefined,
        page: awardPage,
        pageSize: 20,
      }),
    enabled: tab === "awards",
  });

  const invalidateDefs = () =>
    queryClient.invalidateQueries({ queryKey: ["so-badge-defs"] });
  const invalidateAwards = () =>
    queryClient.invalidateQueries({ queryKey: ["so-badge-awards"] });

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const openEdit = (b: BadgeDefinition) => {
    setEditing(b);
    setFormOpen(true);
  };
  const openAward = (badgeId?: string) => {
    if (!classId) {
      toast.error(t("studentOps.badges.requireClass"));
      return;
    }
    setAwardBadgeId(badgeId || "");
    setAwardOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
            <Medal className="h-4 w-4 text-primary" />
          </div>
          <ClassSelector value={classId} onChange={onClassChange} />
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => openAward()}>
            <Award className="h-4 w-4 mr-1" /> {t("studentOps.badges.award")}
          </Button>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4 mr-1" /> {t("studentOps.badges.create")}
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="definitions">
            {t("studentOps.badges.definitions")}
          </TabsTrigger>
          <TabsTrigger value="awards">
            {t("studentOps.badges.history")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="definitions" className="space-y-3">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <Select
                  value={badgeType}
                  onValueChange={(v) => {
                    setBadgeType(v);
                    setDefPage(1);
                  }}
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue placeholder={t("studentOps.badges.type")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                    {TYPES.map((ty) => (
                      <SelectItem key={ty} value={ty}>
                        {t(
                          ty === "red_scarf"
                            ? "studentOps.badges.typeRedScarf"
                            : "studentOps.badges.typeSchoolBased",
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={category}
                  onValueChange={(v) => {
                    setCategory(v);
                    setDefPage(1);
                  }}
                >
                  <SelectTrigger className="w-[150px]">
                    <SelectValue
                      placeholder={t("studentOps.badges.category")}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {t(badgeCategoryKey(c))}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {defQuery.isLoading ? (
                <LoadingRow />
              ) : defQuery.isError ? (
                <ErrorBox />
              ) : defQuery.data?.items.length === 0 ? (
                <EmptyState
                  title={t("studentOps.badges.definitionsEmpty")}
                  action={
                    <Button size="sm" onClick={openCreate}>
                      <Plus className="h-4 w-4 mr-1" />{" "}
                      {t("studentOps.badges.create")}
                    </Button>
                  }
                />
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("studentOps.badges.name")}</TableHead>
                        <TableHead>{t("studentOps.badges.type")}</TableHead>
                        <TableHead>{t("studentOps.badges.category")}</TableHead>
                        <TableHead>{t("studentOps.badges.points")}</TableHead>
                        <TableHead>{t("studentOps.badges.status")}</TableHead>
                        <TableHead className="text-right">
                          {t("studentOps.actions")}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {defQuery.data?.items.map((b) => (
                        <TableRow key={b.id}>
                          <TableCell className="font-medium">
                            {b.name}
                          </TableCell>
                          <TableCell>
                            {b.badgeType === "red_scarf"
                              ? t("studentOps.badges.typeRedScarf")
                              : t("studentOps.badges.typeSchoolBased")}
                          </TableCell>
                          <TableCell>
                            {t(badgeCategoryKey(b.category))}
                          </TableCell>
                          <TableCell>+{b.pointsAwarded}</TableCell>
                          <TableCell>
                            <StatusBadge
                              value={b.isActive ? "approved" : "cancelled"}
                              label={
                                b.isActive
                                  ? t("studentOps.badges.active")
                                  : t("studentOps.badges.inactive")
                              }
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex justify-end gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openAward(b.id)}
                                aria-label={t("studentOps.badges.award")}
                              >
                                <Award className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openEdit(b)}
                                aria-label={t("studentOps.badges.edit")}
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                              {b.isActive && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setDeactivateTarget(b)}
                                  aria-label={t("studentOps.badges.deactivate")}
                                >
                                  <Ban className="h-4 w-4 text-destructive" />
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="p-3">
                    <Pagination
                      page={defQuery.data?.page || 1}
                      pageSize={defQuery.data?.pageSize || 20}
                      total={defQuery.data?.total || 0}
                      onPageChange={setDefPage}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="awards" className="space-y-3">
          <Card>
            <CardContent className="p-0">
              {awardQuery.isLoading ? (
                <LoadingRow />
              ) : awardQuery.isError ? (
                <ErrorBox />
              ) : awardQuery.data?.items.length === 0 ? (
                <EmptyState title={t("studentOps.badges.historyEmpty")} />
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("studentOps.badges.student")}</TableHead>
                        <TableHead>{t("studentOps.badges.badge")}</TableHead>
                        <TableHead>
                          {t("studentOps.badges.awardDate")}
                        </TableHead>
                        <TableHead>{t("studentOps.badges.reason")}</TableHead>
                        <TableHead className="text-right">
                          {t("studentOps.actions")}
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {awardQuery.data?.items.map((a) => (
                        <TableRow key={a.id}>
                          <TableCell className="font-medium">
                            {a.studentName}
                          </TableCell>
                          <TableCell>{a.badgeDefinitionName}</TableCell>
                          <TableCell>{a.awardDate}</TableCell>
                          <TableCell className="max-w-[220px] truncate text-muted-foreground">
                            {a.reason || "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setRevokeTarget(a.id)}
                              aria-label={t("studentOps.badges.revoke")}
                            >
                              <RotateCcw className="h-4 w-4 text-destructive" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="p-3">
                    <Pagination
                      page={awardQuery.data?.page || 1}
                      pageSize={awardQuery.data?.pageSize || 20}
                      total={awardQuery.data?.total || 0}
                      onPageChange={setAwardPage}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <BadgeDefinitionFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        editing={editing}
        onSaved={() => {
          invalidateDefs();
        }}
      />

      <BadgeAwardDialog
        open={awardOpen}
        onOpenChange={setAwardOpen}
        classId={classId}
        presetBadgeId={awardBadgeId}
        onDone={(ok) => {
          invalidateAwards();
          invalidateDefs();
          if (ok) {
            queryClient.invalidateQueries({ queryKey: ["so-credit-accounts"] });
            queryClient.invalidateQueries({ queryKey: ["so-credit-txns"] });
          }
        }}
      />

      <AlertDialog
        open={!!deactivateTarget}
        onOpenChange={(open) => !open && setDeactivateTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("studentOps.badges.deactivate")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("studentOps.badges.deactivateConfirm")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("studentOps.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!deactivateTarget) return;
                deleteBadgeDefinition(deactivateTarget.id)
                  .then(() => {
                    toast.success(t("studentOps.badges.deleted"));
                    invalidateDefs();
                  })
                  .catch((e: Error) => toast.error(e.message))
                  .finally(() => setDeactivateTarget(null));
              }}
            >
              {t("studentOps.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={!!revokeTarget}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("studentOps.badges.revoke")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("studentOps.badges.revokeConfirm")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("studentOps.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!revokeTarget) return;
                revokeBadgeAward(revokeTarget)
                  .then(() => {
                    toast.success(t("studentOps.badges.revokeSuccess"));
                    invalidateAwards();
                    queryClient.invalidateQueries({
                      queryKey: ["so-credit-accounts"],
                    });
                    queryClient.invalidateQueries({
                      queryKey: ["so-credit-txns"],
                    });
                  })
                  .catch((e: Error) => {
                    toast.error(
                      e.message.includes("credit_rollback_failed")
                        ? t("studentOps.badges.rollbackFailed")
                        : e.message,
                    );
                    invalidateAwards();
                  })
                  .finally(() => setRevokeTarget(null));
              }}
            >
              {t("studentOps.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function LoadingRow() {
  const { t } = useLocale();
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin mr-2" />{" "}
      {t("studentOps.loading")}
    </div>
  );
}

function ErrorBox() {
  const { t } = useLocale();
  return (
    <div className="p-4">
      <Alert variant="destructive">
        <AlertTitle>{t("studentOps.loadError")}</AlertTitle>
      </Alert>
    </div>
  );
}

/* ── 章定义 创建/编辑 弹窗 ── */
interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: BadgeDefinition | null;
  onSaved: () => void;
}

function BadgeDefinitionFormDialog({
  open,
  onOpenChange,
  editing,
  onSaved,
}: FormDialogProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [badgeType, setBadgeType] = useState("school_based");
  const [category, setCategory] = useState("moral");
  const [points, setPoints] = useState(10);
  const [minGrade, setMinGrade] = useState("");
  const [maxGrade, setMaxGrade] = useState("");
  const [isActive, setIsActive] = useState(true);

  // 打开时同步 editing
  useEffect(() => {
    if (open) {
      setName(editing?.name || "");
      setDescription(editing?.description || "");
      setBadgeType(editing?.badgeType || "school_based");
      setCategory(editing?.category || "moral");
      setPoints(editing?.pointsAwarded ?? 10);
      setMinGrade(editing?.minGrade || "");
      setMaxGrade(editing?.maxGrade || "");
      setIsActive(editing?.isActive ?? true);
    }
  }, [open, editing]);

  const mutation = useMutation({
    mutationFn: (body: BadgeDefinitionInput) =>
      editing
        ? updateBadgeDefinition(editing.id, body)
        : createBadgeDefinition(body),
    onSuccess: () => {
      toast.success(
        editing
          ? t("studentOps.badges.updateSuccess")
          : t("studentOps.badges.createSuccess"),
      );
      queryClient.invalidateQueries({ queryKey: ["so-badge-defs"] });
      onSaved();
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = () => {
    if (!name.trim()) {
      toast.error(t("studentOps.required"));
      return;
    }
    if (!points || points < 1) {
      toast.error(t("studentOps.positiveNumber"));
      return;
    }
    mutation.mutate({
      name: name.trim(),
      description: description || null,
      badgeType,
      category,
      pointsAwarded: points,
      minGrade: minGrade || null,
      maxGrade: maxGrade || null,
      isActive,
      sortOrder: 0,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {editing
              ? t("studentOps.badges.edit")
              : t("studentOps.badges.create")}
          </DialogTitle>
          <DialogDescription>
            {editing
              ? t("studentOps.badges.edit")
              : t("studentOps.badges.create")}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.badges.name")} *</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("studentOps.badges.namePlaceholder")}
            />
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.badges.description")}</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.badges.type")}</Label>
              <Select value={badgeType} onValueChange={setBadgeType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="red_scarf">
                    {t("studentOps.badges.typeRedScarf")}
                  </SelectItem>
                  <SelectItem value="school_based">
                    {t("studentOps.badges.typeSchoolBased")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.badges.category")}</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {t(badgeCategoryKey(c))}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.badges.points")} *</Label>
            <Input
              type="number"
              min={1}
              value={points}
              onChange={(e) => setPoints(Number(e.target.value))}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.badges.minGrade")}</Label>
              <Input
                value={minGrade}
                onChange={(e) => setMinGrade(e.target.value)}
                placeholder={t("studentOps.gradeMinPlaceholder")}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.badges.maxGrade")}</Label>
              <Input
                value={maxGrade}
                onChange={(e) => setMaxGrade(e.target.value)}
                placeholder={t("studentOps.gradeMaxPlaceholder")}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("studentOps.cancel")}
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending && (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            )}
            {t("studentOps.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── 颁章弹窗（单人或批量） ── */
interface AwardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  presetBadgeId: string;
  onDone: (ok: boolean) => void;
}

function BadgeAwardDialog({
  open,
  onOpenChange,
  classId,
  presetBadgeId,
  onDone,
}: AwardDialogProps) {
  const { t } = useLocale();
  const [badgeId, setBadgeId] = useState("");
  const [awardDate, setAwardDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [reason, setReason] = useState("");
  const [studentIds, setStudentIds] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      setBadgeId(presetBadgeId || "");
      setAwardDate(new Date().toISOString().slice(0, 10));
      setReason("");
      setStudentIds([]);
    }
  }, [open, presetBadgeId]);

  const { data: badges } = useQuery({
    queryKey: ["so-badge-defs", "", "", 1],
    queryFn: () =>
      listBadgeDefinitions({ isActive: true, page: 1, pageSize: 200 }),
  });

  const mutation = useMutation({
    mutationFn: () =>
      awardBadges({
        studentIds,
        badgeDefinitionId: badgeId,
        awardDate,
        reason: reason || null,
      }),
    onSuccess: (res) => {
      if (res.failCount > 0) {
        toast.warning(
          t("studentOps.badges.awardFailed", { count: res.failCount }),
        );
      }
      if (res.successCount > 0) {
        toast.success(
          t("studentOps.badges.awardSuccess", { count: res.successCount }),
        );
      }
      onDone(true);
      onOpenChange(false);
    },
    onError: (e: Error) => {
      toast.error(e.message);
      onDone(false);
    },
  });

  const submit = () => {
    if (!classId) {
      toast.error(t("studentOps.badges.requireClass"));
      return;
    }
    if (!badgeId) {
      toast.error(t("studentOps.badges.selectBadge"));
      return;
    }
    if (studentIds.length === 0) {
      toast.error(t("studentOps.badges.noStudents"));
      return;
    }
    mutation.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("studentOps.badges.awardTitle")}</DialogTitle>
          <DialogDescription>
            <Users className="inline h-4 w-4 mr-1" />
            {t("studentOps.badges.award")}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.badges.selectBadge")} *</Label>
            <Select value={badgeId || undefined} onValueChange={setBadgeId}>
              <SelectTrigger>
                <SelectValue placeholder={t("studentOps.badges.selectBadge")} />
              </SelectTrigger>
              <SelectContent>
                {(badges?.items ?? []).map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.name}（+{b.pointsAwarded}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.badges.awardDate")} *</Label>
              <Input
                type="date"
                value={awardDate}
                onChange={(e) => setAwardDate(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.badges.reason")}</Label>
              <Input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={t("studentOps.badges.reasonPlaceholder")}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.badges.selectStudents")} *</Label>
            <StudentMultiPicker
              classId={classId}
              selected={studentIds}
              onChange={setStudentIds}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("studentOps.cancel")}
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending && (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            )}
            {t("studentOps.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
