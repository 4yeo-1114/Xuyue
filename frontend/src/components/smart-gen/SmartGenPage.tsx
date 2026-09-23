import { useState, useCallback, useRef, useEffect } from "react";
import { SmartGenHeader } from "./SmartGenHeader";
import { RequirementInput } from "./RequirementInput";
import { AIIntegrationPanel } from "./AIIntegrationPanel";
import { GenerationHistory } from "./GenerationHistory";
import { GenType } from "./smartGenData";
import { useAIGenerate } from "@/hooks/useAIGenerate";
import { useClasses } from "@/hooks/useClasses";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import type { AiGenerationHistoryItem } from "@/services/api";

interface GenParams {
  content: string;
  objective: string;
  studentProfile: string;
  requirements: string;
}

interface Props {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
}

const GEN_TYPES = new Set(["courseware", "worksheet", "multimedia"]);

export function SmartGenPage({
  selectedSubject,
  selectedClass,
  onNavChange,
}: Props) {
  const { t } = useLocale();
  const { data: classes = [] } = useClasses();
  const selectedClassName =
    classes.find((c) => c.id === selectedClass)?.name || "";
  const [genType, setGenType] = useState<GenType>("courseware");
  const [showPreview, setShowPreview] = useState(false);
  const [historySignal, setHistorySignal] = useState(0);
  const lastParamsRef = useRef<GenParams | null>(null);
  const {
    isGenerating,
    streamedContent,
    title,
    progress,
    generate,
    cancel,
    reset,
    loadExisting,
  } = useAIGenerate();

  const handleGenerate = useCallback(
    (params: GenParams) => {
      lastParamsRef.current = params;
      setShowPreview(true);
      generate({ ...params, genType, subject: selectedSubject });
    },
    [genType, generate, selectedSubject],
  );

  const handleRegenerate = useCallback(() => {
    if (!lastParamsRef.current) {
      toast.info(t("smartGen.regenerate.needGenerateFirst"));
      return;
    }
    reset();
    generate({ ...lastParamsRef.current, genType, subject: selectedSubject });
  }, [genType, generate, reset, t, selectedSubject]);

  // 生成完成后刷新右侧历史列表
  useEffect(() => {
    if (!isGenerating && streamedContent) {
      setHistorySignal((v) => v + 1);
    }
  }, [isGenerating, streamedContent]);

  // 点击历史条目 → 回填标题/正文并切换对应生成类型
  const handleLoadHistory = useCallback(
    (item: AiGenerationHistoryItem) => {
      if (GEN_TYPES.has(item.gen_type)) {
        setGenType(item.gen_type as GenType);
      }
      loadExisting(item.title || "", item.content || "");
      setShowPreview(true);
    },
    [loadExisting],
  );

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
      <div className="space-y-6 min-w-0">
        <SmartGenHeader
          genType={genType}
          onGenTypeChange={setGenType}
          selectedClass={selectedClassName}
          selectedSubject={selectedSubject}
        />

        <RequirementInput
          onGenerate={handleGenerate}
          isGenerating={isGenerating}
        />

        {showPreview && (
          <div className="animate-fade-in">
            <AIIntegrationPanel
              isGenerating={isGenerating}
              streamedContent={streamedContent}
              title={title}
              subject={selectedSubject}
              genType={genType}
              progress={progress}
              onCancel={cancel}
              onRegenerate={handleRegenerate}
            />
          </div>
        )}
      </div>

      <div className="xl:sticky xl:top-6">
        <GenerationHistory
          refreshSignal={historySignal}
          onLoad={handleLoadHistory}
        />
      </div>
    </div>
  );
}
