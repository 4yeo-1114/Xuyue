import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/hooks/use-toast";
import { Lock, Loader2, Mail, Smartphone } from "lucide-react";
import { z } from "zod";
import { useProjectBranding } from "@/contexts/ProjectBrandingContext";
import { BrandLogo } from "@/components/BrandLogo";
import { useLocale } from "@/contexts/LocaleContext";
import { LanguageToggle } from "@/components/LanguageToggle";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { buildGradeLevels } from "@/i18n";

// 免审核自助注册只开放「任课教师」（= 不挂靠学校的独立老师）。
// 其余角色都能经 is_school_admin() 拿到后台权限，可选即等于公网自封管理员（提权）。
// 后端闸门在 app/schemas/auth.py 的 RegisterRole（Literal）；此处不再保留第二份角色清单。
const REGISTER_ROLE = "任课教师";

/** 轻量验证码倒计时（不引新依赖）。seconds 归零即恢复可点。 */
function useCountdown() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (seconds <= 0) return;
    const id = setTimeout(() => setSeconds((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [seconds]);
  const start = (n = 60) => setSeconds(n);
  return { seconds, start };
}

export default function Auth() {
  const REMEMBER_KEY = "grade_buddy_remembered_credentials";
  const [email, setEmail] = useState(() => {
    try {
      const saved = localStorage.getItem(REMEMBER_KEY);
      return saved ? (JSON.parse(saved).email ?? "") : "";
    } catch {
      return "";
    }
  });
  const [password, setPassword] = useState(() => {
    try {
      const saved = localStorage.getItem(REMEMBER_KEY);
      return saved ? (JSON.parse(saved).password ?? "") : "";
    } catch {
      return "";
    }
  });
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [mode, setMode] = useState<"login" | "register" | "phone">("login");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regEmailCode, setRegEmailCode] = useState("");
  const [regDisplayName, setRegDisplayName] = useState("");
  const [regSubject, setRegSubject] = useState("");
  const [regGrade, setRegGrade] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCode, setPhoneCode] = useState("");
  const [sendingRegCode, setSendingRegCode] = useState(false);
  const [sendingPhoneCode, setSendingPhoneCode] = useState(false);
  const regCode = useCountdown();
  const phoneCd = useCountdown();
  const { signIn, register, sendCode, phoneLogin } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const { projectName } = useProjectBranding();
  const { t, locale } = useLocale();
  const gradeLevels = useMemo(() => buildGradeLevels(locale), [locale]);

  const emailSchema = z.string().email(t("auth.invalidEmail"));
  const passwordSchema = z.string().min(6, t("auth.passwordMin"));
  const phoneSchema = z.string().regex(/^1\d{10}$/, t("auth.invalidPhone"));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const emailResult = emailSchema.safeParse(email);
    if (!emailResult.success) {
      toast({
        title: t("auth.inputError"),
        description: emailResult.error.errors[0].message,
        variant: "destructive",
      });
      return;
    }

    const passwordResult = passwordSchema.safeParse(password);
    if (!passwordResult.success) {
      toast({
        title: t("auth.inputError"),
        description: passwordResult.error.errors[0].message,
        variant: "destructive",
      });
      return;
    }

    setSubmitting(true);
    try {
      const { error } = await signIn(email, password);
      if (error) {
        const msg =
          error.message.includes("密码") ||
          error.message.toLowerCase().includes("password")
            ? t("auth.wrongCredentials")
            : error.message;
        toast({
          title: t("auth.loginFailed"),
          description: msg,
          variant: "destructive",
        });
      } else {
        if (remember) {
          localStorage.setItem(
            REMEMBER_KEY,
            JSON.stringify({ email, password }),
          );
        } else {
          localStorage.removeItem(REMEMBER_KEY);
        }
        navigate("/");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();

    const emailResult = emailSchema.safeParse(regEmail);
    if (!emailResult.success) {
      toast({
        title: t("auth.inputError"),
        description: emailResult.error.errors[0].message,
        variant: "destructive",
      });
      return;
    }

    const passwordResult = passwordSchema.safeParse(regPassword);
    if (!passwordResult.success) {
      toast({
        title: t("auth.inputError"),
        description: passwordResult.error.errors[0].message,
        variant: "destructive",
      });
      return;
    }

    if (!regEmailCode.trim()) {
      toast({
        title: t("auth.inputError"),
        description: t("auth.emailCodeRequired"),
        variant: "destructive",
      });
      return;
    }

    setSubmitting(true);
    try {
      const { error } = await register({
        email: regEmail,
        password: regPassword,
        email_code: regEmailCode.trim(),
        display_name: regDisplayName || undefined,
        role: REGISTER_ROLE,
        teaching_subject: regSubject.trim() || undefined,
        teaching_grade: regGrade.trim() || undefined,
      });
      if (error) {
        const msg =
          error.message.includes("已注册") ||
          error.message.toLowerCase().includes("registered")
            ? t("auth.emailExists")
            : error.message.includes("频繁") ||
                error.message.toLowerCase().includes("too many")
              ? t("auth.registerRateLimited")
              : // 科目为自由填写，服务端长度上限（32）是唯一闸门；此处透出原文，
                // 否则用户只看到笼统的「注册失败」，不知道该改哪里
                error.message.includes("科目")
                ? error.message
                : error.message.includes("验证码")
                  ? error.message
                  : t("auth.registerFailed");
        toast({
          title: t("auth.registerFailed"),
          description: msg,
          variant: "destructive",
        });
      } else {
        toast({ title: t("auth.registerSuccess") });
        navigate("/");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendRegCode = async () => {
    const emailResult = emailSchema.safeParse(regEmail);
    if (!emailResult.success) {
      toast({
        title: t("auth.inputError"),
        description: emailResult.error.errors[0].message,
        variant: "destructive",
      });
      return;
    }
    setSendingRegCode(true);
    const { error } = await sendCode(regEmail, "email", "register");
    setSendingRegCode(false);
    if (error) {
      toast({
        title: t("auth.sendCodeFailed"),
        description: error.message,
        variant: "destructive",
      });
    } else {
      regCode.start(60);
      toast({ title: t("auth.sendCodeSent") });
    }
  };

  const handleSendPhoneCode = async () => {
    const phoneResult = phoneSchema.safeParse(phone);
    if (!phoneResult.success) {
      toast({
        title: t("auth.inputError"),
        description: phoneResult.error.errors[0].message,
        variant: "destructive",
      });
      return;
    }
    setSendingPhoneCode(true);
    const { error } = await sendCode(phone, "sms", "login");
    setSendingPhoneCode(false);
    if (error) {
      toast({
        title: t("auth.sendCodeFailed"),
        description: error.message,
        variant: "destructive",
      });
    } else {
      phoneCd.start(60);
      toast({ title: t("auth.sendCodeSent") });
    }
  };

  const handlePhoneLogin = async (e: React.FormEvent) => {
    e.preventDefault();

    const phoneResult = phoneSchema.safeParse(phone);
    if (!phoneResult.success) {
      toast({
        title: t("auth.inputError"),
        description: phoneResult.error.errors[0].message,
        variant: "destructive",
      });
      return;
    }
    if (!phoneCode.trim()) {
      toast({
        title: t("auth.inputError"),
        description: t("auth.smsCodeRequired"),
        variant: "destructive",
      });
      return;
    }

    setSubmitting(true);
    try {
      const { error } = await phoneLogin(phone, phoneCode.trim());
      if (error) {
        toast({
          title: t("auth.loginFailed"),
          description: error.message,
          variant: "destructive",
        });
      } else {
        navigate("/");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 relative">
      <div className="absolute top-4 right-4">
        <LanguageToggle />
      </div>

      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <BrandLogo className="w-16 h-16 mx-auto mb-4" alt="" />
          <h1 className="text-2xl font-bold text-foreground">{projectName}</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {t("app.subtitle")}
          </p>
        </div>

        <div className="bg-card rounded-xl border border-border p-6 shadow-sm">
          <Tabs
            value={mode}
            onValueChange={(v) => setMode(v as "login" | "register")}
          >
            <TabsList className="grid w-full grid-cols-3 mb-6">
              <TabsTrigger value="login">{t("auth.login")}</TabsTrigger>
              <TabsTrigger value="register">
                {t("auth.registerTab")}
              </TabsTrigger>
              <TabsTrigger value="phone">{t("auth.phoneLogin")}</TabsTrigger>
            </TabsList>

            <TabsContent value="login">
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">{t("auth.email")}</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      placeholder={t("auth.emailPlaceholder")}
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-10"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">{t("auth.password")}</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="password"
                      type="password"
                      placeholder={t("auth.passwordPlaceholder")}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-10"
                      required
                    />
                  </div>
                </div>

                <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer select-none">
                  <Checkbox
                    checked={remember}
                    onCheckedChange={(c) => setRemember(!!c)}
                  />
                  <span>{t("auth.rememberMe")}</span>
                </label>

                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting && (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  )}
                  {submitting ? t("auth.signingIn") : t("auth.login")}
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="register">
              <form onSubmit={handleRegister} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="regEmail">{t("auth.email")}</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="regEmail"
                      type="email"
                      placeholder={t("auth.emailPlaceholder")}
                      value={regEmail}
                      onChange={(e) => setRegEmail(e.target.value)}
                      className="pl-10"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="regEmailCode">{t("auth.emailCode")}</Label>
                  <div className="flex gap-2">
                    <Input
                      id="regEmailCode"
                      placeholder={t("auth.emailCodePlaceholder")}
                      value={regEmailCode}
                      onChange={(e) => setRegEmailCode(e.target.value)}
                      className="flex-1"
                      maxLength={6}
                      inputMode="numeric"
                      required
                    />
                    <Button
                      type="button"
                      variant="outline"
                      className="shrink-0"
                      onClick={handleSendRegCode}
                      disabled={regCode.seconds > 0 || sendingRegCode}
                    >
                      {sendingRegCode ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : regCode.seconds > 0 ? (
                        `${regCode.seconds}s`
                      ) : (
                        t("auth.sendCode")
                      )}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="regPassword">{t("auth.password")}</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="regPassword"
                      type="password"
                      placeholder={t("auth.passwordPlaceholder")}
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      className="pl-10"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="regDisplayName">
                    {t("auth.displayName")}
                  </Label>
                  <Input
                    id="regDisplayName"
                    placeholder={t("auth.displayNamePlaceholder")}
                    value={regDisplayName}
                    onChange={(e) => setRegDisplayName(e.target.value)}
                  />
                </div>

                {/* 角色无选项：自助注册只开放「任课教师」，故不做成下拉框（单选项下拉框是死交互） */}
                <div className="space-y-2">
                  <Label>{t("auth.role")}</Label>
                  <p className="text-sm text-muted-foreground">
                    {t("auth.register.roleSubjectTeacher")}
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="regSubject">{t("auth.subject")}</Label>
                  <Input
                    id="regSubject"
                    placeholder={t("auth.subjectPlaceholder")}
                    value={regSubject}
                    onChange={(e) => setRegSubject(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label>{t("auth.grade")}</Label>
                  <Select value={regGrade} onValueChange={setRegGrade}>
                    <SelectTrigger>
                      <SelectValue placeholder={t("auth.gradePlaceholder")} />
                    </SelectTrigger>
                    <SelectContent>
                      {gradeLevels.flatMap((level) =>
                        level.grades.map((grade) => (
                          <SelectItem key={grade.value} value={grade.value}>
                            {grade.label}
                          </SelectItem>
                        )),
                      )}
                    </SelectContent>
                  </Select>
                </div>

                <p className="text-xs text-muted-foreground">
                  {t("auth.registerHint")}
                </p>

                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting && (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  )}
                  {submitting ? t("auth.registering") : t("auth.register")}
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="phone">
              <form onSubmit={handlePhoneLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="phone">{t("auth.phone")}</Label>
                  <div className="relative">
                    <Smartphone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      id="phone"
                      type="tel"
                      placeholder={t("auth.phonePlaceholder")}
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="pl-10"
                      maxLength={11}
                      inputMode="numeric"
                      required
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="phoneCode">{t("auth.smsCode")}</Label>
                  <div className="flex gap-2">
                    <Input
                      id="phoneCode"
                      placeholder={t("auth.smsCodePlaceholder")}
                      value={phoneCode}
                      onChange={(e) => setPhoneCode(e.target.value)}
                      className="flex-1"
                      maxLength={6}
                      inputMode="numeric"
                      required
                    />
                    <Button
                      type="button"
                      variant="outline"
                      className="shrink-0"
                      onClick={handleSendPhoneCode}
                      disabled={phoneCd.seconds > 0 || sendingPhoneCode}
                    >
                      {sendingPhoneCode ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : phoneCd.seconds > 0 ? (
                        `${phoneCd.seconds}s`
                      ) : (
                        t("auth.sendCode")
                      )}
                    </Button>
                  </div>
                </div>

                <p className="text-xs text-muted-foreground">
                  {t("auth.phoneLoginHint")}
                </p>

                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting && (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  )}
                  {submitting ? t("auth.signingIn") : t("auth.phoneLogin")}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
