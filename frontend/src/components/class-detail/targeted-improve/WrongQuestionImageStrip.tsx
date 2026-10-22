import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Image as ImageIcon, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/contexts/LocaleContext";
import { getLatestWrongQuestions } from "@/services/api";
import { gradingImageUrl } from "@/services/gradingApi";

interface WrongQuestionImageStripProps {
  classId: string;
  studentName: string;
  subject: string;
}

/**
 * 错题图集（20261022 用户要求「结合图片，纯文字太繁琐」）：
 * 拉该生该科最近一场考试的错题图（student_wrong_questions.image_url），
 * 横向缩略图条呈现，点击弹大图（题图 + 答案图并排）。没图就不占位。
 */
export function WrongQuestionImageStrip({
  classId,
  studentName,
  subject,
}: WrongQuestionImageStripProps) {
  const { t } = useLocale();
  const [preview, setPreview] = useState<{
    title: string;
    question: string;
    answer?: string | null;
  } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["targeted-wrong-images", classId, studentName, subject],
    queryFn: () => getLatestWrongQuestions(classId, studentName, subject),
    enabled: !!classId && !!studentName && !!subject,
  });

  const items = (data?.questions || []).filter((q) => !!q.image_url);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed bg-muted/20 px-3 py-3 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {t("targeted.wrongImages.loading")}
      </div>
    );
  }
  if (items.length === 0) return null;

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <ImageIcon className="h-4 w-4 text-primary" />
        <span className="text-[15px] font-semibold">
          {t("targeted.wrongImages.title")}
        </span>
        <span className="text-xs text-muted-foreground">
          {t("targeted.wrongImages.hint", { count: items.length })}
        </span>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {items.map((q, i) => {
          const src = gradingImageUrl(q.image_url || undefined);
          return (
            <button
              key={`${q.title}-${i}`}
              type="button"
              className="w-[170px] shrink-0 overflow-hidden rounded-lg border border-border/70 bg-white text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
              onClick={() =>
                setPreview({
                  title: q.title || t("targeted.wrongImages.item", { index: i + 1 }),
                  question: src,
                  answer: q.answer_url ? gradingImageUrl(q.answer_url) : null,
                })
              }
            >
              <img
                src={src}
                alt={q.title || ""}
                loading="lazy"
                className="h-[112px] w-full border-b border-border/50 bg-white object-cover object-top"
              />
              <div className="space-y-1 p-2">
                <p className="truncate text-xs font-medium text-foreground">
                  {q.title || t("targeted.wrongImages.item", { index: i + 1 })}
                </p>
                {q.knowledge_point_name ? (
                  <Badge
                    variant="secondary"
                    className="max-w-full truncate text-[10px] font-normal"
                  >
                    {q.knowledge_point_name}
                  </Badge>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>

      <Dialog
        open={!!preview}
        onOpenChange={(open) => {
          if (!open) setPreview(null);
        }}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{preview?.title}</DialogTitle>
          </DialogHeader>
          <div className="grid max-h-[70vh] gap-3 overflow-y-auto md:grid-cols-2">
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">
                {t("targeted.wrongImages.questionImage")}
              </p>
              {preview ? (
                <img
                  src={preview.question}
                  alt={preview.title}
                  className="w-full rounded-lg border bg-white"
                />
              ) : null}
            </div>
            {preview?.answer ? (
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">
                  {t("targeted.wrongImages.answerImage")}
                </p>
                <img
                  src={preview.answer}
                  alt={preview.title}
                  className="w-full rounded-lg border bg-white"
                />
              </div>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

export default WrongQuestionImageStrip;
