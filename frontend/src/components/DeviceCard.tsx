import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface DeviceCardProps {
  title: string;
  description: string;
  icon: LucideIcon;
  status: "online" | "offline" | "scanning" | "error";
  statusText: string;
  onClick?: () => void;
  className?: string;
}

const statusStyles = {
  online: "bg-success",
  offline: "bg-muted-foreground",
  scanning: "bg-primary animate-pulse",
  error: "bg-destructive animate-pulse",
};

export function DeviceCard({
  title,
  description,
  icon: Icon,
  status,
  statusText,
  onClick,
  className,
}: DeviceCardProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative overflow-hidden rounded-xl bg-card p-6 card-elevated cursor-pointer border border-border/50",
        "transition-all duration-300 hover:border-primary/30",
        className
      )}
    >
      {/* Background gradient on hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      
      <div className="relative z-10">
        {/* Header with icon and status */}
        <div className="flex items-start justify-between mb-4">
          <div className="p-3 rounded-xl bg-primary/10 text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors duration-300">
            <Icon className="w-6 h-6" />
          </div>
          <div className="flex items-center gap-2">
            <span className={cn("w-2.5 h-2.5 rounded-full", statusStyles[status])} />
            <span className="text-sm text-muted-foreground">{statusText}</span>
          </div>
        </div>

        {/* Title and description */}
        <h3 className="text-lg font-semibold text-foreground mb-1">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}
