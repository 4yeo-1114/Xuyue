import { cn } from "@/lib/utils";

/**
 * 品牌商标图（叙阅 logo）。
 * 统一从 /public/brand-logo.jpg 加载，容器按需传 className 控制尺寸/圆角，
 * 图片 object-contain 保持完整商标不变形。
 */
export function BrandLogo({
  className,
  alt = "叙阅",
}: {
  className?: string;
  alt?: string;
}) {
  return (
    <img
      src="/brand-logo.jpg"
      alt={alt}
      draggable={false}
      className={cn("object-contain select-none shrink-0", className)}
    />
  );
}
