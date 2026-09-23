import { useLocale } from "@/contexts/LocaleContext";
import { Loader2 } from "lucide-react";
import { Alert, AlertTitle } from "@/components/ui/alert";

export function LoadingRow() {
  const { t } = useLocale();
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin mr-2" />{" "}
      {t("studentOps.loading")}
    </div>
  );
}

export function ErrorBox() {
  const { t } = useLocale();
  return (
    <div className="p-4">
      <Alert variant="destructive">
        <AlertTitle>{t("studentOps.loadError")}</AlertTitle>
      </Alert>
    </div>
  );
}
