/* ── Shared types for AI chat data cards ── */

export interface StudentCardData {
  id: string;
  name: string;
  student_number: string;
  class_name: string;
  scores: { exam_title: string; score: number; total: number }[];
  weak_points: string[];
  wrong_count: number;
  risk_level?: "上升" | "稳定" | "下滑";
  target_score?: number;
}

export interface KnowledgeCardData {
  id: string;
  name: string;
  code: string;
  mastery: number;
  is_weak: boolean;
  difficulty: string;
  level: string;
  common_errors: string;
  related_students?: number;
}

export interface ClassOverviewData {
  class_name: string;
  student_count: number;
  avg_score: number;
  weak_students: { name: string; score: number }[];
  weak_knowledge: string[];
  risk_stats?: { rising: number; stable: number; declining: number };
}

export interface WrongQuestionData {
  student_name: string;
  subject: string;
  content: string;
  error_type: string;
  correct_answer: string;
  student_answer: string;
}

export interface QuestionItem {
  id: string;
  content: string;
  type: string;
  difficulty: number;
  score: number;
  use_count: number;
  knowledge_points: string[];
  subject: string;
}

export interface QuestionListData {
  total: number;
  questions: QuestionItem[];
}

export type DataCard =
  | { type: "student"; data: StudentCardData }
  | { type: "knowledge"; data: KnowledgeCardData }
  | { type: "class_overview"; data: ClassOverviewData }
  | { type: "wrong_questions"; data: { questions: WrongQuestionData[] } }
  | { type: "question_list"; data: QuestionListData };
