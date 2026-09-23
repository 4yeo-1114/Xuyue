import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";

interface SubjectCardProps {
  name: string;
  icon: LucideIcon;
  count: number;
  color: string;
  bgClass: string;
  onClick?: () => void;
}

export function SubjectCard({
  name,
  icon: Icon,
  count,
  color,
  bgClass,
  onClick,
}: SubjectCardProps) {
  const { t } = useLocale();
  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative overflow-hidden rounded-xl p-5 cursor-pointer",
        "transition-all duration-300 hover:scale-[1.02]",
        bgClass,
      )}
    >
      {/* Decorative circle */}
      <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full bg-white/10 group-hover:scale-125 transition-transform duration-500" />
      <div className="absolute -right-8 -bottom-8 w-32 h-32 rounded-full bg-white/5 group-hover:scale-110 transition-transform duration-700" />

      <div className="relative z-10">
        <Icon className="w-8 h-8 text-white/90 mb-3" />
        <h3 className="text-lg font-bold text-white mb-1">{name}</h3>
        <p className="text-white/70 text-sm">
          {t("home.subjectCard.pendingCount", { count })}
        </p>
      </div>
    </div>
  );
}
