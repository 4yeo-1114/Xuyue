import { cn } from "@/lib/utils";
import { Languages } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";

interface LanguageToggleProps {
  className?: string;
}

/** 中英文切换（按当前登录账号隔离，偏好存服务端） */
export function LanguageToggle({ className }: LanguageToggleProps) {
  const { locale, toggleLocale, t } = useLocale();

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className={cn("h-9 gap-1.5 text-sm shrink-0", className)}
      onClick={() => void toggleLocale()}
      title={t("lang.switch")}
    >
      <Languages className="w-4 h-4 shrink-0" />
      <span>{locale === "en" ? "中文" : "EN"}</span>
    </Button>
  );
}
