export type WarningLevel = "red" | "yellow" | "green";
export type TicketStatus = "pending" | "in_progress" | "resolved" | "closed";

export interface WarningAlert {
  id: string;
  schoolName: string;
  /** 学校版预警中心：后端返回班级名，局版无此字段 */
  className?: string;
  grade: string;
  subject: string;
  metric: string;
  value: number;
  threshold: number;
  level: WarningLevel;
  createdAt: string;
  status: string;
}

export interface TaskTicket {
  id: string;
  title: string;
  description: string;
  level: WarningLevel;
  targetSchool: string;
  targetPerson: string;
  deadline: string;
  status: TicketStatus;
  createdBy: string;
  createdAt: string;
}
