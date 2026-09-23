from app.models.user import User, gen_uuid
from app.models.class_model import Class
from app.models.student import Student
from app.models.exam import Exam
from app.models.ai_generation_history import AiGenerationHistory
from app.models.exam_score import ExamScore
from app.models.wrong_question import WrongQuestion
from app.models.exam_question_template import ExamQuestionTemplate
from app.models.subject_unit import SubjectUnit
from app.models.knowledge_point import KnowledgePoint
from app.models.teaching_resource import TeachingResource
from app.models.system_config import SystemConfig
from app.models.feature_flag import FeatureFlag
from app.models.user_role import UserRole
from app.models.profile import Profile
from app.models.class_teacher import ClassTeacher
from app.models.essay_rubric import EssayRubric
from app.models.system_settings import SystemSettings
from app.models.todo_item import TodoItem
from app.models.lesson_plan import LessonPlan
from app.models.textbook_catalog import TextbookCatalog
from app.models.prep_plan import PrepPlan
from app.models.student_analysis import StudentAnalysis, StudentScoreHistory
from app.models.targeted_improvement import TargetedImprovementReport, TargetedRecommendation
from app.models.class_review import ClassReviewSession
from app.models.class_analysis import ClassAnalysisReport
from app.models.grading_daily_stat import GradingDailyStat

# ── DL1 学校/区域锚表（D1/F1 区域多校视图数据层前置）────────────
from app.models.school import Region, School

# ── DL4a C2 校本题库表（school_question_banks，唯一键 school_id+fingerprint）────
from app.models.school_question_bank import SchoolQuestionBank

# ── 种春风三域新模型（integration 收口统一注册）────────────
# A 画像域
from app.models.student_portfolio import StudentPortfolio
from app.models.student_growth_record import StudentGrowthRecord
from app.models.indicator_definition import IndicatorDefinition
from app.models.report_snapshot import ReportSnapshot
from app.models.assessment_comment import AssessmentComment
from app.models.mentor import Mentor
# B 测评域
from app.models.assessment_definition import AssessmentDefinition
from app.models.assessment_session import AssessmentSession
from app.models.assessment_result import AssessmentResult
from app.models.assessment_answer import AssessmentAnswer
from app.models.parent_student import ParentStudent
# C 学生运营域
from app.models.badge_definition import BadgeDefinition
from app.models.badge_award import BadgeAward
from app.models.credit_account import CreditAccount
from app.models.credit_transaction import CreditTransaction
from app.models.reward_product import RewardProduct
from app.models.redemption_record import RedemptionRecord
from app.models.practice_record import PracticeRecord
from app.models.campus_club import CampusClub
from app.models.club_enrollment import ClubEnrollment
from app.models.club_attendance import ClubAttendance
from app.models.book_borrow import BookBorrow
from app.models.reading_record import ReadingRecord
from app.models.health_check import HealthCheck
from app.models.student_task import StudentTask
from app.models.attendance_record import AttendanceRecord
# E03/E14 合规域：访问留痕（敏感读取 + 高危行权）
from app.models.access_log import AccessLog
# G4-A AI 对话落库（agent_conversations / agent_conversation_messages / agent_audit_logs）
from app.models.ai_conversation import AiConversation, AiConversationMessage, AiAuditLog
# R1 逐题响应日志（response_logs，学情预警/bandit 错题推荐数据底座）
from app.models.response_log import ResponseLog
# R6a 错题→知识点桥（wrong_question_kp_bridge，历史错题跨库匹配 PG 知识点结果落表）
from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge
# R6b contextual bandit 状态表（bandit_arm_stats，LinUCB arm 状态与推荐统计）
from app.models.bandit_arm_stats import BanditArmStats

# ── P3-B 模型-库对齐：student_memories 补注册 ────────────
from app.models.student_memory import StudentMemory

# ── 流水阅卷 / 集体阅卷（flow_batches/flow_questions/flow_items/flow_assignments/flow_reviews/flow_arbitrations）────
from app.models.flow_grading import (
    FlowBatch,
    FlowQuestion,
    FlowItem,
    FlowAssignment,
    FlowReview,
    FlowArbitration,
)

__all__ = [
    "User",
    "gen_uuid",
    "Class",
    "Student",
    "Exam",
    "AiGenerationHistory",
    "ExamScore",
    "WrongQuestion",
    "ExamQuestionTemplate",
    "SubjectUnit",
    "KnowledgePoint",
    "TeachingResource",
    "SystemConfig",
    "FeatureFlag",
    "UserRole",
    "Profile",
    "ClassTeacher",
    "EssayRubric",
    "SystemSettings",
    "TodoItem",
    "LessonPlan",
    "TextbookCatalog",
    "PrepPlan",
    "StudentAnalysis",
    "StudentScoreHistory",
    "TargetedImprovementReport",
    "TargetedRecommendation",
    "ClassReviewSession",
    "ClassAnalysisReport",
    "GradingDailyStat",
    # DL1 学校/区域锚表
    "Region",
    "School",
    # DL4a C2 校本题库表
    "SchoolQuestionBank",
    # 种春风三域新模型
    "StudentPortfolio",
    "StudentGrowthRecord",
    "IndicatorDefinition",
    "ReportSnapshot",
    "AssessmentComment",
    "Mentor",
    "AssessmentDefinition",
    "AssessmentSession",
    "AssessmentResult",
    "AssessmentAnswer",
    "ParentStudent",
    "BadgeDefinition",
    "BadgeAward",
    "CreditAccount",
    "CreditTransaction",
    "RewardProduct",
    "RedemptionRecord",
    "PracticeRecord",
    "CampusClub",
    "ClubEnrollment",
    "ClubAttendance",
    "BookBorrow",
    "ReadingRecord",
    "HealthCheck",
    "StudentTask",
    "AttendanceRecord",
    "AccessLog",
    # G4-A AI 对话落库
    "AiConversation",
    "AiConversationMessage",
    "AiAuditLog",
    # R1 逐题响应日志
    "ResponseLog",
    # R6a 错题→知识点桥
    "WrongQuestionKpBridge",
    # R6b contextual bandit 状态表
    "BanditArmStats",
    # P3-B 模型-库对齐：student_memories 补注册
    "StudentMemory",
    # 流水阅卷 / 集体阅卷
    "FlowBatch",
    "FlowQuestion",
    "FlowItem",
    "FlowAssignment",
    "FlowReview",
    "FlowArbitration",
]
