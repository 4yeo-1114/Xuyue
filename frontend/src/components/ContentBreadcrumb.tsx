import { NAV_ITEMS } from "@/components/Sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Home } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";

interface ContentBreadcrumbProps {
  activeNavId: string;
  onNavChange: (id: string) => void;
}

export function ContentBreadcrumb({ activeNavId, onNavChange }: ContentBreadcrumbProps) {
  const { t } = useLocale();

  if (activeNavId === "home") return null;

  let groupLabel = "";
  let childLabel = "";
  let groupFirstChildId = "";

  for (const group of NAV_ITEMS) {
    if (group.id === activeNavId) {
      groupLabel = t(`nav.${group.id}`, undefined, group.label);
      break;
    }
    const child = group.children?.find((c) => c.id === activeNavId);
    if (child) {
      groupLabel = t(`nav.${group.id}`, undefined, group.label);
      childLabel = t(`nav.${child.id}`, undefined, child.label);
      groupFirstChildId = group.children?.[0]?.id || "";
      break;
    }
  }

  if (!groupLabel) return null;

  return (
    <Breadcrumb className="mb-4">
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink
            className="cursor-pointer flex items-center gap-1 text-muted-foreground hover:text-foreground"
            onClick={() => onNavChange("home")}
          >
            <Home className="w-3.5 h-3.5" />
            {t("common.home")}
          </BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        {childLabel ? (
          <>
            <BreadcrumbItem>
              <BreadcrumbLink
                className="cursor-pointer hover:text-foreground"
                onClick={() => onNavChange(groupFirstChildId)}
              >
                {groupLabel}
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{childLabel}</BreadcrumbPage>
            </BreadcrumbItem>
          </>
        ) : (
          <BreadcrumbItem>
            <BreadcrumbPage>{groupLabel}</BreadcrumbPage>
          </BreadcrumbItem>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
