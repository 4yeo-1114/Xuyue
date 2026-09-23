import type {
  WarningAlert,
  TaskTicket,
  WarningLevel,
  TicketStatus,
} from "@/types/bureau";

const WARNINGS_KEY = "grade_buddy_warnings";
const TICKETS_KEY = "grade_buddy_tickets";

const mockWarnings: WarningAlert[] = [
  {
    id: "w1",
    schoolName: "红星小学",
    grade: "六年级",
    subject: "数学",
    metric: "平均分",
    value: 48,
    threshold: 60,
    level: "red",
    createdAt: "2026-06-18",
    status: "active",
  },
  {
    id: "w2",
    schoolName: "阳光小学",
    grade: "五年级",
    subject: "语文",
    metric: "及格率",
    value: 62,
    threshold: 70,
    level: "yellow",
    createdAt: "2026-06-17",
    status: "active",
  },
  {
    id: "w3",
    schoolName: "开发区实验学校",
    grade: "四年级",
    subject: "英语",
    metric: "优秀率",
    value: 18,
    threshold: 25,
    level: "yellow",
    createdAt: "2026-06-16",
    status: "active",
  },
  {
    id: "w4",
    schoolName: "中心三小",
    grade: "三年级",
    subject: "数学",
    metric: "平均分",
    value: 55,
    threshold: 60,
    level: "red",
    createdAt: "2026-06-15",
    status: "active",
  },
  {
    id: "w5",
    schoolName: "和平路小学",
    grade: "六年级",
    subject: "科学",
    metric: "合格率",
    value: 85,
    threshold: 80,
    level: "green",
    createdAt: "2026-06-14",
    status: "resolved",
  },
  {
    id: "w6",
    schoolName: "东城小学",
    grade: "五年级",
    subject: "数学",
    metric: "平均分",
    value: 52,
    threshold: 60,
    level: "red",
    createdAt: "2026-06-13",
    status: "active",
  },
  {
    id: "w7",
    schoolName: "春晖路小学",
    grade: "四年级",
    subject: "语文",
    metric: "及格率",
    value: 68,
    threshold: 70,
    level: "yellow",
    createdAt: "2026-06-12",
    status: "active",
  },
  {
    id: "w8",
    schoolName: "龙港实验学校",
    grade: "三年级",
    subject: "英语",
    metric: "优秀率",
    value: 30,
    threshold: 25,
    level: "green",
    createdAt: "2026-06-11",
    status: "resolved",
  },
];

const mockTickets: TaskTicket[] = [
  {
    id: "t1",
    title: "红星小学六年级数学平均分严重偏低",
    description: "连续两次考试平均分低于60，需跟进教学整改",
    level: "red",
    targetSchool: "红星小学",
    targetPerson: "张校长",
    deadline: "2026-07-01",
    status: "in_progress",
    createdBy: "系统",
    createdAt: "2026-06-18",
  },
  {
    id: "t2",
    title: "中心三小数学教学质量督导",
    description: "三年级数学平均分持续低位运行",
    level: "red",
    targetSchool: "中心三小",
    targetPerson: "李校长",
    deadline: "2026-07-05",
    status: "pending",
    createdBy: "教育局王主任",
    createdAt: "2026-06-15",
  },
  {
    id: "t3",
    title: "阳光小学语文及格率提升计划",
    description: "五年级语文及格率未达区级基准线",
    level: "yellow",
    targetSchool: "阳光小学",
    targetPerson: "赵教导主任",
    deadline: "2026-07-15",
    status: "pending",
    createdBy: "系统",
    createdAt: "2026-06-17",
  },
  {
    id: "t4",
    title: "开发区实验学校英语教学经验分享",
    description: "英语优秀率接近达标，建议总结推广",
    level: "yellow",
    targetSchool: "开发区实验学校",
    targetPerson: "刘教研员",
    deadline: "2026-07-20",
    status: "resolved",
    createdBy: "教研室",
    createdAt: "2026-06-16",
  },
  {
    id: "t5",
    title: "和平路小学科学教学示范确认",
    description: "科学合格率持续达标，确认示范校资格",
    level: "green",
    targetSchool: "和平路小学",
    targetPerson: "王校长",
    deadline: "2026-06-30",
    status: "closed",
    createdBy: "系统",
    createdAt: "2026-06-14",
  },
];

function loadFromStorage<T>(key: string, fallback: T[]): T[] {
  try {
    const raw = localStorage.getItem(key);
    if (raw) return JSON.parse(raw) as T[];
  } catch {
    /* ignore */
  }
  localStorage.setItem(key, JSON.stringify(fallback));
  return fallback;
}

function saveToStorage<T>(key: string, data: T[]): void {
  localStorage.setItem(key, JSON.stringify(data));
}

export function getWarnings(): WarningAlert[] {
  return loadFromStorage(WARNINGS_KEY, mockWarnings);
}

export function getTickets(): TaskTicket[] {
  return loadFromStorage(TICKETS_KEY, mockTickets);
}

export function createTicket(
  ticket: Omit<TaskTicket, "id" | "createdAt">,
): TaskTicket {
  const tickets = getTickets();
  const newTicket: TaskTicket = {
    ...ticket,
    status: ticket.status ?? "pending",
    id: `t${Date.now()}`,
    createdAt: new Date().toISOString().split("T")[0],
  };
  tickets.unshift(newTicket);
  saveToStorage(TICKETS_KEY, tickets);
  return newTicket;
}

export function updateTicketStatus(id: string, status: TicketStatus): void {
  const tickets = getTickets();
  const idx = tickets.findIndex((t) => t.id === id);
  if (idx !== -1) {
    tickets[idx].status = status;
    saveToStorage(TICKETS_KEY, tickets);
  }
}
