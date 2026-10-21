import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { changePassword, updateProfile } from "@/services/api";
import { KeyRound, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName, translateSystemRole } from "@/i18n";

const TEACHING_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "地理",
  "历史",
  "政治",
  "生物",
  "科学",
  "信息",
  "物理",
  "化学",
] as const;

export function PersonalSettingsPage() {
  const { user, refreshUser, sendCode, bindPhone } = useAuth();
  const { t, locale } = useLocale();
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [sendingPhoneCode, setSendingPhoneCode] = useState(false);
  const [phoneCd, setPhoneCd] = useState(0);
  const [subject, setSubject] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [personalEmail, setPersonalEmail] = useState("");
  const [saving, setSaving] = useState(false);

  const [pwdOpen, setPwdOpen] = useState(false);
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdLoading, setPwdLoading] = useState(false);

  useEffect(() => {
    if (!user) return;
    setDisplayName(user.display_name || "");
    setPhone(user.phone || "");
    setSubject(user.teaching_subject || "");
    setJobTitle(user.job_title || "");
    setPersonalEmail(user.personal_email || "");
  }, [user]);

  // 绑定手机号验证码倒计时
  useEffect(() => {
    if (phoneCd <= 0) return;
    const id = setTimeout(() => setPhoneCd((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [phoneCd]);

  const resetPwdFields = () => {
    setOldPwd("");
    setNewPwd("");
    setConfirmPwd("");
  };

  const handleSendPhoneCode = async () => {
    if (!/^1\d{10}$/.test(phone.trim())) {
      toast.error(t("settings.personal.toast.invalidPhone"));
      return;
    }
    setSendingPhoneCode(true);
    const { error } = await sendCode(phone.trim(), "sms", "bind");
    setSendingPhoneCode(false);
    if (error) {
      toast.error(error.message);
    } else {
      setPhoneCd(60);
      toast.success(t("settings.personal.toast.codeSent"));
    }
  };

  const handleSaveProfile = async () => {
    const newPhone = phone.trim();
    const currentPhone = (user?.phone || "").trim();
    // 手机号变更需短信验证码（合规：手机号作为可验证唯一身份）
    if (newPhone && newPhone !== currentPhone) {
      if (!phoneCode.trim()) {
        toast.error(t("settings.personal.toast.codeRequired"));
        return;
      }
      const { error } = await bindPhone(newPhone, phoneCode.trim());
      if (error) {
        toast.error(error.message);
        return;
      }
      setPhoneCode("");
    }
    setSaving(true);
    try {
      await updateProfile({
        display_name: displayName.trim() || null,
        teaching_subject: subject === "__none__" || !subject ? "__CLEAR__" : subject,
        job_title: jobTitle.trim() || null,
        personal_email: personalEmail.trim() || null,
      });
      await refreshUser();
      queryClient.invalidateQueries({ queryKey: ["class-teachers"] });
      toast.success(t("settings.personal.toast.saved"));
    } catch (e: any) {
      toast.error(e?.message || t("settings.personal.toast.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async () => {
    if (!oldPwd.trim()) {
      toast.error(t("settings.personal.toast.oldPwdRequired"));
      return;
    }
    if (newPwd.length < 6) {
      toast.error(t("settings.personal.toast.newPwdMin"));
      return;
    }
    if (newPwd !== confirmPwd) {
      toast.error(t("settings.personal.toast.pwdMismatch"));
      return;
    }
    setPwdLoading(true);
    try {
      await changePassword({ old_password: oldPwd, new_password: newPwd });
      toast.success(t("settings.personal.toast.pwdChanged"));
      resetPwdFields();
      setPwdOpen(false);
    } catch (e: any) {
      toast.error(e?.message || t("settings.personal.toast.pwdChangeFailed"));
    } finally {
      setPwdLoading(false);
    }
  };

  if (!user) {
    return (
      <div className="flex min-h-[calc(100vh-8rem)] w-full items-center justify-center text-muted-foreground text-sm">
        {t("settings.personal.loginRequired")}
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] w-full flex-col items-center justify-center px-4 py-8">
      <div className="w-full max-w-2xl space-y-6 animate-in fade-in duration-300">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="text-center sm:text-left">
            <h1 className="text-2xl font-bold text-foreground">{t("settings.personal.title")}</h1>
            <p className="text-sm text-muted-foreground mt-1">{t("settings.personal.subtitle")}</p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="shrink-0 gap-2 self-center sm:self-start"
            onClick={() => {
              resetPwdFields();
              setPwdOpen(true);
            }}
          >
            <KeyRound className="w-4 h-4" />
            {t("settings.personal.changePassword")}
          </Button>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{t("settings.personal.basicInfo")}</CardTitle>
            <CardDescription>{t("settings.personal.basicInfoDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>{t("settings.personal.name")}</Label>
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={t("settings.personal.namePlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("settings.personal.account")}</Label>
              <Input value={user.email} readOnly className="bg-muted/50 cursor-not-allowed" />
            </div>
            <div className="space-y-2">
              <Label>{t("settings.personal.jobTitle")}</Label>
              <Input
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder={t("settings.personal.jobTitlePlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("settings.personal.phone")}</Label>
              <Input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder={t("settings.personal.phoneOptional")}
              />
              {phone.trim() && phone.trim() !== (user?.phone || "").trim() ? (
                <div className="flex gap-2">
                  <Input
                    placeholder={t("settings.personal.codePlaceholder")}
                    value={phoneCode}
                    onChange={(e) => setPhoneCode(e.target.value)}
                    maxLength={6}
                    inputMode="numeric"
                    className="flex-1"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="shrink-0"
                    onClick={handleSendPhoneCode}
                    disabled={phoneCd > 0 || sendingPhoneCode}
                  >
                    {sendingPhoneCode ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : phoneCd > 0 ? (
                      `${phoneCd}s`
                    ) : (
                      t("settings.personal.sendCode")
                    )}
                  </Button>
                </div>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label>{t("settings.personal.systemRole")}</Label>
              <div className="flex flex-wrap gap-2 p-2 border rounded-md bg-muted/50 min-h-10 items-center">
                {user?.roles && user.roles.length > 0 ? (
                  user.roles.map((r) => (
                    <span
                      key={r}
                      className="px-2 py-1 bg-primary/10 text-primary text-xs rounded border border-primary/20"
                    >
                      {translateSystemRole(locale, r)}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-muted-foreground">{t("settings.personal.noRoles")}</span>
                )}
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t("settings.personal.personalEmail")}</Label>
              <Input
                value={personalEmail}
                onChange={(e) => setPersonalEmail(e.target.value)}
                placeholder={t("settings.personal.personalEmailPlaceholder")}
                type="email"
              />
            </div>
            <div className="space-y-2">
              <Label>{t("settings.personal.teachingSubject")}</Label>
              <Select value={subject || "__none__"} onValueChange={(v) => setSubject(v === "__none__" ? "" : v)}>
                <SelectTrigger>
                  <SelectValue placeholder={t("settings.personal.selectSubject")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">{t("settings.personal.subjectUnset")}</SelectItem>
                  {TEACHING_SUBJECTS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {translateSubjectName(locale, s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={handleSaveProfile} disabled={saving}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              {t("settings.personal.saveProfile")}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={pwdOpen}
        onOpenChange={(open) => {
          setPwdOpen(open);
          if (!open) resetPwdFields();
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("settings.personal.pwd.title")}</DialogTitle>
            <DialogDescription>{t("settings.personal.pwd.desc")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="pwd-old">{t("settings.personal.pwd.old")}</Label>
              <Input
                id="pwd-old"
                type="password"
                value={oldPwd}
                onChange={(e) => setOldPwd(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="pwd-new">{t("settings.personal.pwd.new")}</Label>
              <Input
                id="pwd-new"
                type="password"
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="pwd-confirm">{t("settings.personal.pwd.confirm")}</Label>
              <Input
                id="pwd-confirm"
                type="password"
                value={confirmPwd}
                onChange={(e) => setConfirmPwd(e.target.value)}
                autoComplete="new-password"
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => setPwdOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="button" onClick={handleChangePassword} disabled={pwdLoading}>
              {pwdLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              {t("settings.personal.pwd.confirmBtn")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
