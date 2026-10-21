import type {
  ReferenceLayoutAnswerSlot,
  ReferenceLayoutPage,
  ReferenceLayoutQuestion,
  ReferenceLayoutRegion,
} from "@/services/gradingApi";

/** 布局模板列表/保存响应元数据（不含完整 layout） */
export type LayoutTemplateMeta = {
  id: string;
  name: string;
  subject?: string;
  class_id?: string;
  source_folder?: string;
  created_at?: string;
  updated_at?: string;
  page_count?: number;
};

/** 布局模板详情（含完整 layout JSON） */
export type LayoutTemplateDetail = LayoutTemplateMeta & {
  layout: {
    version?: number;
    pages?: ReferenceLayoutPage[];
  };
};

type Box = [number, number, number, number];
type Size = [number, number];

function isSize(size: unknown): size is Size {
  return (
    Array.isArray(size) &&
    size.length >= 2 &&
    Number.isFinite(Number(size[0])) &&
    Number.isFinite(Number(size[1])) &&
    Number(size[0]) > 0 &&
    Number(size[1]) > 0
  );
}

function isBbox(box: unknown): box is Box {
  return (
    Array.isArray(box) &&
    box.length >= 4 &&
    box.slice(0, 4).every((v) => Number.isFinite(Number(v)))
  );
}

function asBox(box: unknown): Box {
  return [
    Number(box[0]),
    Number(box[1]),
    Number(box[2]),
    Number(box[3]),
  ];
}

/** 按目标图尺寸缩放 bbox（同尺寸/缺尺寸时原样返回，四舍五入到整像素） */
export function scaleBbox(
  bbox: Box,
  fromSize: Size,
  toSize: Size,
): Box {
  if (
    !isBbox(bbox) ||
    !isSize(fromSize) ||
    !isSize(toSize) ||
    (fromSize[0] === toSize[0] && fromSize[1] === toSize[1])
  ) {
    return asBox(bbox);
  }
  const sx = toSize[0] / fromSize[0];
  const sy = toSize[1] / fromSize[1];
  return [
    Math.round(Number(bbox[0]) * sx),
    Math.round(Number(bbox[1]) * sy),
    Math.round(Number(bbox[2]) * sx),
    Math.round(Number(bbox[3]) * sy),
  ];
}

function scaleRegion(
  region: ReferenceLayoutRegion,
  fromSize: Size,
  toSize: Size,
): ReferenceLayoutRegion {
  return {
    ...region,
    bbox: scaleBbox(asBox(region.bbox), fromSize, toSize),
  };
}

function scaleSlot(
  slot: ReferenceLayoutAnswerSlot,
  fromSize: Size,
  toSize: Size,
): ReferenceLayoutAnswerSlot {
  return {
    ...slot,
    bbox: slot.bbox ? scaleBbox(asBox(slot.bbox), fromSize, toSize) : slot.bbox,
    regions: (slot.regions || []).map((region) =>
      scaleRegion(region, fromSize, toSize),
    ),
  };
}

function scaleQuestion(
  question: ReferenceLayoutQuestion,
  fromSize: Size,
  toSize: Size,
): ReferenceLayoutQuestion {
  return {
    ...question,
    regions: (question.regions || []).map((region) =>
      scaleRegion(region, fromSize, toSize),
    ),
    answer_slots: (question.answer_slots || []).map((slot) =>
      scaleSlot(slot, fromSize, toSize),
    ),
  };
}

function templateSize(page: ReferenceLayoutPage): Size {
  const size = page?.image_size;
  return isSize(size) ? ([Number(size[0]), Number(size[1])] as Size) : [0, 0];
}

/**
 * 把模板页套到当前考试的布局页上（按 page_no 匹配）。
 * 保留当前页的 filename / image_url / image_size / page_no，只替换 questions；
 * 模板图与当前图尺寸不同时按比例缩放 bbox。未匹配到的当前页原样保留。
 */
export function applyTemplateToPages(
  currentPages: ReferenceLayoutPage[],
  templatePages: ReferenceLayoutPage[],
): ReferenceLayoutPage[] {
  const current = Array.isArray(currentPages) ? currentPages : [];
  const template = Array.isArray(templatePages) ? templatePages : [];
  const byPageNo = new Map<number, ReferenceLayoutPage>();
  for (const page of template) {
    if (page && Number.isFinite(Number(page.page_no))) {
      byPageNo.set(Number(page.page_no), page);
    }
  }
  return current.map((page) => {
    const matched = byPageNo.get(Number(page.page_no));
    // 模板页缺 questions 时保留当前页（confirm_reference_layout 要求每页至少一个题目框）
    if (!matched || !Array.isArray(matched.questions) || !matched.questions.length) {
      return { ...page };
    }
    const fromSize = templateSize(matched);
    const toSize = templateSize(page);
    return {
      ...page,
      questions: matched.questions.map((question) =>
        scaleQuestion(question, fromSize, toSize),
      ),
    };
  });
}

/** 从模板详情里取出可套用的布局页数组 */
export function templateLayoutPages(
  detail: LayoutTemplateDetail | null | undefined,
): ReferenceLayoutPage[] {
  const pages = detail?.layout?.pages;
  return Array.isArray(pages) ? pages : [];
}

/** 保存模板时把当前布局页打包成后端 layout JSON */
export function packLayoutForTemplate(
  pages: ReferenceLayoutPage[],
): { version: number; pages: ReferenceLayoutPage[] } {
  return {
    version: 1,
    pages: (Array.isArray(pages) ? pages : []).map((page) => ({ ...page })),
  };
}
