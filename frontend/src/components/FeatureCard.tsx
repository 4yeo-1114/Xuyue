import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface FeatureCardProps {
  title: string;
  icon: LucideIcon;
  secondaryIcon?: LucideIcon;
  value?: string | number;
  variant: "orange" | "coral" | "red" | "teal" | "light";
  onClick?: () => void;
  className?: string;
}

const variantStyles = {
  orange: "bg-gradient-to-br from-amber-400 to-orange-500 text-white",
  coral: "bg-gradient-to-br from-orange-400 to-rose-500 text-white",
  red: "bg-gradient-to-br from-rose-500 to-red-600 text-white",
  teal: "bg-gradient-to-br from-teal-100 to-cyan-100 text-teal-700",
  light: "bg-gradient-to-br from-slate-50 to-slate-100 text-slate-600",
};

export function FeatureCard({
  title,
  icon: Icon,
  secondaryIcon: SecondaryIcon,
  value,
  variant,
  onClick,
  className,
}: FeatureCardProps) {
  const isLight = variant === "teal" || variant === "light";

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative overflow-hidden rounded-2xl p-5 cursor-pointer text-left transition-all duration-300",
        "hover:scale-[1.02] hover:shadow-lg",
        "min-w-[160px] h-[120px] flex flex-col justify-between",
        variantStyles[variant],
        className,
      )}
    >
      {/* Icons */}
      <div className="flex items-center gap-2">
        <div
          className={cn(
            "w-8 h-8 rounded-lg flex items-center justify-center",
            isLight ? "bg-white/60" : "bg-white/20",
          )}
        >
          <Icon className="w-5 h-5" />
        </div>
        {SecondaryIcon && (
          <div
            className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center",
              isLight ? "bg-white/60" : "bg-white/20",
            )}
          >
            <SecondaryIcon className="w-5 h-5" />
          </div>
        )}
        {value && (
          <div
            className={cn(
              "px-3 py-1 rounded-lg text-lg font-bold",
              isLight ? "bg-white/60" : "bg-white/20",
            )}
          >
            {value}
          </div>
        )}
      </div>

      {/* Title */}
      <p className="text-sm font-medium mt-auto">{title}</p>
    </button>
  );
}
