import { useState } from "react";
import { cn } from "@/lib/utils";
import { 
  Camera, 
  RotateCw, 
  ZoomIn, 
  ZoomOut, 
  Settings2,
  Focus,
  Sun,
  Crop
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { useLocale } from "@/contexts/LocaleContext";

interface HighSpeedCameraProps {
  isConnected: boolean;
  className?: string;
}

export function HighSpeedCamera({ isConnected, className }: HighSpeedCameraProps) {
  const { t } = useLocale();
  const [zoom, setZoom] = useState([100]);
  const [brightness, setBrightness] = useState([50]);

  return (
    <div className={cn("space-y-4", className)}>
      <div className="relative aspect-[4/3] rounded-xl bg-muted overflow-hidden border-2 border-dashed border-border">
        {isConnected ? (
          <>
            <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-muted to-muted/80">
              <div className="text-center">
                <Camera className="w-16 h-16 text-muted-foreground mx-auto mb-3 animate-pulse" />
                <p className="text-muted-foreground font-medium">{t("grading.camera.livePreview")}</p>
                <p className="text-sm text-muted-foreground">{t("grading.camera.placeHomework")}</p>
              </div>
            </div>
            
            <div className="absolute inset-8 border-2 border-primary/50 rounded-lg pointer-events-none">
              <div className="absolute -top-1 -left-1 w-4 h-4 border-t-2 border-l-2 border-primary" />
              <div className="absolute -top-1 -right-1 w-4 h-4 border-t-2 border-r-2 border-primary" />
              <div className="absolute -bottom-1 -left-1 w-4 h-4 border-b-2 border-l-2 border-primary" />
              <div className="absolute -bottom-1 -right-1 w-4 h-4 border-b-2 border-r-2 border-primary" />
            </div>

            <div className="absolute top-3 left-3 flex items-center gap-2 px-2 py-1 rounded-full bg-success/90 text-success-foreground text-xs">
              <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
              {t("grading.camera.connected")}
            </div>
          </>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Camera className="w-16 h-16 text-muted-foreground/50 mx-auto mb-3" />
              <p className="text-muted-foreground font-medium">{t("grading.camera.notDetected")}</p>
              <p className="text-sm text-muted-foreground">{t("grading.camera.connectUsb")}</p>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Button 
          size="lg" 
          className="h-14 text-base"
          disabled={!isConnected}
        >
          <Camera className="w-5 h-5 mr-2" />
          {t("grading.camera.capture")}
        </Button>
        <Button 
          size="lg" 
          variant="outline" 
          className="h-14 text-base"
          disabled={!isConnected}
        >
          <RotateCw className="w-5 h-5 mr-2" />
          {t("grading.camera.rotate")}
        </Button>
      </div>

      <div className="p-4 rounded-xl bg-muted/50 space-y-4">
        <div className="flex items-center gap-3">
          <Settings2 className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">{t("grading.camera.settingsTitle")}</span>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground flex items-center gap-2">
                <ZoomIn className="w-4 h-4" /> {t("grading.camera.zoom")}
              </span>
              <span className="text-foreground font-medium">{zoom[0]}%</span>
            </div>
            <Slider
              value={zoom}
              onValueChange={setZoom}
              min={50}
              max={200}
              step={10}
              disabled={!isConnected}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground flex items-center gap-2">
                <Sun className="w-4 h-4" /> {t("grading.camera.brightness")}
              </span>
              <span className="text-foreground font-medium">{brightness[0]}%</span>
            </div>
            <Slider
              value={brightness}
              onValueChange={setBrightness}
              min={0}
              max={100}
              step={5}
              disabled={!isConnected}
            />
          </div>
        </div>

        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={!isConnected}>
            <Focus className="w-4 h-4 mr-1" /> {t("grading.camera.autoFocus")}
          </Button>
          <Button variant="outline" size="sm" disabled={!isConnected}>
            <Crop className="w-4 h-4 mr-1" /> {t("grading.camera.autoCrop")}
          </Button>
        </div>
      </div>
    </div>
  );
}
