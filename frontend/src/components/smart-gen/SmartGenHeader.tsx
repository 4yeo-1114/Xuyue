import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sparkles, ClipboardList, Monitor, Film } from "lucide-react";
import { GenType, GEN_TYPE_OPTIONS } from "./smartGenData";
import { useLocale } from "@/contexts/LocaleContext";

interface Props {
  genType: GenType;
  onGenTypeChange: (t: GenType) => void;
  selectedClass: string;
  selectedSubject: string;
}

const TYPE_ICONS: Record<GenType, React.ElementType> = {
  courseware: Monitor,
  worksheet: ClipboardList,
  multimedia: Film,
};

export function SmartGenHeader({
  genType,
  onGenTypeChange,
  selectedClass,
  selectedSubject,
}: Props) {
  const { t } = useLocale();

  const badgeText =
    [selectedClass, selectedSubject].filter(Boolean).join("") ||
    t("common.selectClassFirst");

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">
              {t("smartGen.header.title")}
            </h1>
            <p className="text-xs text-muted-foreground">
              {t("smartGen.header.subtitle")}
            </p>
          </div>
        </div>
        <Badge variant="outline" className="text-xs">
          {badgeText}
        </Badge>
      </div>

      <div className="flex gap-2" data-tour="sg-gen-types">
        {GEN_TYPE_OPTIONS.map((opt) => {
          const Icon = TYPE_ICONS[opt.value];
          return (
            <Button
              key={opt.value}
              variant={genType === opt.value ? "default" : "outline"}
              size="sm"
              className="text-xs h-8 gap-1.5"
              onClick={() => onGenTypeChange(opt.value)}
            >
              <Icon className="w-3.5 h-3.5" />
              {t(`smartGen.genType.${opt.value}`)}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
