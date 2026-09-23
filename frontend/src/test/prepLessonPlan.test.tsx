import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LessonPlanPage } from "@/components/prep-plan/LessonPlanPage";
import { PREP_LESSON_CONTEXT_KEY } from "@/components/prep-plan/TextbookCatalogPage";
import type { LessonPlanApiRecord, LessonPlanTemplate } from "@/services/api";

const {
  listLessonPlansMock,
  createLessonPlanMock,
  updateLessonPlanMock,
  deleteLessonPlanMock,
  listLessonPlanTemplatesMock,
  aiGenerateLessonPlanOutlineMock,
  aiGenerateLessonPlanFullMock,
  listResourceFoldersMock,
  listResourceFilesMock,
  sendLessonPlanEmailMock,
  getAllUsersMock,
  listTextbookCatalogsMock,
} = vi.hoisted(() => ({
  listLessonPlansMock: vi.fn(),
  createLessonPlanMock: vi.fn(),
  updateLessonPlanMock: vi.fn(),
  deleteLessonPlanMock: vi.fn(),
  listLessonPlanTemplatesMock: vi.fn(),
  aiGenerateLessonPlanOutlineMock: vi.fn(),
  aiGenerateLessonPlanFullMock: vi.fn(),
  listResourceFoldersMock: vi.fn(),
  listResourceFilesMock: vi.fn(),
  sendLessonPlanEmailMock: vi.fn(),
  getAllUsersMock: vi.fn(),
  listTextbookCatalogsMock: vi.fn(),
}));

vi.mock("@/contexts/LocaleContext", () => ({
  useLocale: () => ({ t: (key: string) => key, locale: "zh" }),
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: "u1",
      display_name: "Test Teacher",
      email: "t@e.com",
      roles: ["系统管理员"],
    },
  }),
}));

vi.mock("@/services/api", () => ({
  listLessonPlans: listLessonPlansMock,
  createLessonPlan: createLessonPlanMock,
  updateLessonPlan: updateLessonPlanMock,
  deleteLessonPlan: deleteLessonPlanMock,
  listLessonPlanTemplates: listLessonPlanTemplatesMock,
  aiGenerateLessonPlanOutline: aiGenerateLessonPlanOutlineMock,
  aiGenerateLessonPlanFull: aiGenerateLessonPlanFullMock,
  listResourceFolders: listResourceFoldersMock,
  listResourceFiles: listResourceFilesMock,
  sendLessonPlanEmail: sendLessonPlanEmailMock,
  getAllUsers: getAllUsersMock,
  listTextbookCatalogs: listTextbookCatalogsMock,
}));

const mockRecord: LessonPlanApiRecord = {
  id: "p1",
  user_id: "u1",
  class_id: "c1",
  school_year: "2026-2027",
  term: "上学期",
  grade: "初一",
  subject: "数学",
  title: "1.1 正数和负数",
  teaching_content: "教材版本：人教版\n年级：初一",
  teaching_objectives: "理解正负数的概念",
  key_points: "正负数的表示",
  difficult_points: "数轴上的位置",
  teaching_preparation: "课件",
  teaching_process: "一、课堂导入\n情境引入",
  collective_preparation_advice: "组内讨论",
  blackboard_design: "课题板书",
  teaching_reflection: "课后反思",
  main_author: "Test Teacher",
  deputy_author: "",
  lesson_sequence: "第1课时",
  completed_at: null,
  created_at: "2026-08-31T00:00:00Z",
  updated_at: "2026-08-31T00:00:00Z",
};

const templates: LessonPlanTemplate[] = [
  {
    id: 1,
    name: "新授课通用模板",
    category: "新授课",
    structure: [
      { step: "课堂导入", prompt: "通过情境或复习引入新课" },
      { step: "讲授新课", prompt: "讲解核心知识点" },
      { step: "巩固练习", prompt: "组织课堂练习" },
    ] as unknown as Record<string, unknown>,
    description: "适合常规新授课",
    is_active: true,
  },
];

function setupCatalogContext() {
  sessionStorage.clear();
  sessionStorage.setItem(
    PREP_LESSON_CONTEXT_KEY,
    JSON.stringify({
      subject: "数学",
      grade: "初一",
      edition: "人教版",
      nodeId: 3,
      nodeName: "1.1 正数和负数",
      level: "lesson",
    }),
  );
}

function renderLessonPlan() {
  return render(
    <LessonPlanPage
      selectedSubject="数学"
      selectedGrade="初一"
      selectedClass="c1"
      selectedClassName="初一(1)班"
      onNavChange={() => {}}
    />,
  );
}

describe("LessonPlanPage #48b 教案编辑增强", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listLessonPlansMock.mockResolvedValue([]);
    createLessonPlanMock.mockResolvedValue(mockRecord);
    updateLessonPlanMock.mockResolvedValue(mockRecord);
    listLessonPlanTemplatesMock.mockResolvedValue(templates);
    aiGenerateLessonPlanOutlineMock.mockResolvedValue({});
    aiGenerateLessonPlanFullMock.mockResolvedValue(mockRecord);
    getAllUsersMock.mockResolvedValue([]);
    listResourceFoldersMock.mockResolvedValue([]);
    listResourceFilesMock.mockResolvedValue([]);
    listTextbookCatalogsMock.mockResolvedValue([]);
  });

  it("目录上下文预填：读 sessionStorage 预填课题并自动新建进入编辑器，读后清空", async () => {
    setupCatalogContext();
    renderLessonPlan();

    await waitFor(() => {
      expect(createLessonPlanMock).toHaveBeenCalledWith(
        expect.objectContaining({
          class_id: "c1",
          grade: "初一",
          subject: "数学",
          title: "1.1 正数和负数",
          main_author: "Test Teacher",
        }),
      );
    });

    const titleInput = screen.getByPlaceholderText(
      "prepPlan.lesson.field.titlePlaceholder",
    ) as HTMLInputElement;
    expect(titleInput.value).toBe("1.1 正数和负数");

    expect(sessionStorage.getItem(PREP_LESSON_CONTEXT_KEY)).toBeNull();
  });

  it("模板导航：打开模板抽屉套用后教学过程被填充", async () => {
    setupCatalogContext();
    renderLessonPlan();

    await waitFor(() => {
      expect(createLessonPlanMock).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByText("prepPlan.lesson.templateButton"));

    await waitFor(() => {
      expect(screen.getByText("prepPlan.lesson.templateApply")).toBeTruthy();
    });

    fireEvent.click(screen.getByText("prepPlan.lesson.templateApply"));

    const processTextarea = screen.getByPlaceholderText(
      "prepPlan.lesson.field.teachingProcessPlaceholder",
    ) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(processTextarea.value).toContain("课堂导入");
    });
    expect(processTextarea.value).toContain("讲授新课");
  });

  it("AI 生成：大纲确认后生成完整教案并落库", async () => {
    setupCatalogContext();
    renderLessonPlan();

    await waitFor(() => {
      expect(createLessonPlanMock).toHaveBeenCalled();
    });

    aiGenerateLessonPlanOutlineMock.mockResolvedValueOnce({
      title: "1.1 正数和负数",
      objectives: "理解正负数的意义",
      key_points: "正负数的表示方法",
      difficult_points: "数轴与绝对值",
      process_summary: [
        { step: "课堂导入", point: "生活情境引入" },
        { step: "讲授新课", point: "讲解正负数" },
      ],
    });

    fireEvent.click(screen.getByText("prepPlan.lesson.aiGenerate"));

    await waitFor(() => {
      expect(aiGenerateLessonPlanOutlineMock).toHaveBeenCalledWith(
        expect.objectContaining({
          subject: "数学",
          grade: "初一",
          edition: "人教版",
          lesson_title: "1.1 正数和负数",
          lesson_sequence: "第1课时",
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText("prepPlan.lesson.outline.title")).toBeTruthy();
    });

    fireEvent.click(
      screen.getByText("prepPlan.lesson.outline.confirmAndGenerate"),
    );

    await waitFor(() => {
      expect(aiGenerateLessonPlanFullMock).toHaveBeenCalledWith(
        expect.objectContaining({
          class_id: "c1",
          subject: "数学",
          lesson_title: "1.1 正数和负数",
        }),
      );
    });

    const fullCall = aiGenerateLessonPlanFullMock.mock
      .calls[0][0] as { outline: string };
    expect(fullCall.outline).toContain("课题：1.1 正数和负数");
    expect(fullCall.outline).toContain("教学目标");
    expect(fullCall.outline).toContain("教学过程概要");
  });
});
