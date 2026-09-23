// Mock data for class management settings page

export interface MockStudent {
  id: string;
  studentNumber: string;
  name: string;
  gender: "男" | "女";
  tier: "A" | "B" | "C";
  status: "正常" | "预警" | "转出" | "休学";
  birthday?: string;
  phone?: string;
  parentName?: string;
  parentPhone?: string;
  address?: string;
  enrollDate?: string;
  seatRow?: number;
  seatCol?: number;
  role?: string;
  tags?: string[];
  notes?: string;
  history?: { date: string; action: string; operator: string }[];
}

export interface MockTeacher {
  id: string;
  name: string;
  subject: string;
  role: "班主任" | "科任老师" | "助教";
  permissions: string[];
  avatar?: string;
}

export interface MockClassInfo {
  id: string;
  name: string;
  myRole: "班主任" | "科任";
  studentCount: number;
  maleCount: number;
  femaleCount: number;
  tierA: number;
  tierB: number;
  tierC: number;
  warningCount: number;
  status: string;
  lastUpdate: string;
  syncStatus: string;
  teachers: MockTeacher[];
  students: MockStudent[];
}

export interface MockSyncLog {
  id: string;
  time: string;
  action: string;
  result: "成功" | "失败" | "部分成功";
  detail: string;
}

const generateStudents = (classNum: number, count: number): MockStudent[] => {
  const surnames = ["李", "王", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "马", "朱", "胡", "郭", "林", "何", "高", "罗"];
  const givenMale = ["明", "华", "强", "伟", "刚", "磊", "鹏", "辉", "涛", "杰"];
  const givenFemale = ["芳", "静", "丽", "娟", "敏", "霞", "婷", "燕", "玲", "颖"];
  const tiers: ("A" | "B" | "C")[] = ["A", "B", "C"];
  const statuses: ("正常" | "预警")[] = ["正常", "预警"];

  return Array.from({ length: count }, (_, i) => {
    const gender = i % 3 === 0 ? "女" : "男";
    const surname = surnames[i % surnames.length];
    const given = gender === "男" ? givenMale[i % givenMale.length] : givenFemale[i % givenFemale.length];
    const tier = i < 12 ? "A" : i < 30 ? "B" : "C";
    const isWarning = tier === "C" && i % 5 === 0;

    return {
      id: `s-${classNum}-${i}`,
      studentNumber: `2023${classNum.toString().padStart(2, "0")}${(i + 1).toString().padStart(2, "0")}`,
      name: `${surname}${given}${i > 9 ? "" : ""}`,
      gender,
      tier,
      status: isWarning ? "预警" : "正常",
      birthday: `20${10 + (i % 3)}-${String((i % 12) + 1).padStart(2, "0")}-${String((i % 28) + 1).padStart(2, "0")}`,
      phone: i % 3 === 0 ? `138****${String(1000 + i).slice(-4)}` : undefined,
      parentName: `${surname}大${gender === "男" ? "明" : "丽"}（${i % 2 === 0 ? "父亲" : "母亲"}）`,
      parentPhone: `139****${String(5000 + i).slice(-4)}`,
      enrollDate: "2023-09",
      seatRow: Math.floor(i / 6) + 1,
      seatCol: (i % 6) + 1,
      role: i === 0 ? "班长" : i === 1 ? "学习委员" : undefined,
      tags: isWarning ? ["学业预警"] : [],
      notes: isWarning ? "需加强基础训练，建议增加课后辅导" : "",
      history: [
        { date: "2024-03-15", action: `分层调整：${tiers[(tiers.indexOf(tier) + 1) % 3]}层→${tier}层`, operator: "张老师" },
        { date: "2024-02-20", action: "学期初信息更新", operator: "系统" },
      ],
    };
  });
};

export const MOCK_CLASSES: MockClassInfo[] = [
  {
    id: "c1",
    name: "初一(1)班",
    myRole: "班主任",
    studentCount: 36,
    maleCount: 20,
    femaleCount: 16,
    tierA: 12,
    tierB: 18,
    tierC: 6,
    warningCount: 3,
    status: "正常教学",
    lastUpdate: "昨日（新增1名学生，调整2人分层）",
    syncStatus: "已与钉钉同步（36人全部匹配）",
    teachers: [
      { id: "t1", name: "我（张老师）", subject: "语文", role: "班主任", permissions: ["全部权限"] },
      { id: "t2", name: "李老师", subject: "数学", role: "科任老师", permissions: ["查看本班数据", "布置作业"] },
      { id: "t3", name: "王老师", subject: "英语", role: "科任老师", permissions: ["查看本班数据", "布置作业"] },
      { id: "t4", name: "赵老师", subject: "历史", role: "科任老师", permissions: ["查看本班数据", "布置作业"] },
    ],
    students: generateStudents(1, 36),
  },
  {
    id: "c3",
    name: "初一(3)班",
    myRole: "班主任",
    studentCount: 36,
    maleCount: 20,
    femaleCount: 16,
    tierA: 12,
    tierB: 18,
    tierC: 6,
    warningCount: 5,
    status: "正常教学",
    lastUpdate: "昨日（新增1名学生，调整2人分层）",
    syncStatus: "已与钉钉同步（36人全部匹配）",
    teachers: [
      { id: "t1", name: "我（张老师）", subject: "语文", role: "班主任", permissions: ["全部权限"] },
      { id: "t5", name: "张老师", subject: "数学", role: "科任老师", permissions: ["查看本班数据", "布置作业"] },
      { id: "t6", name: "赵老师", subject: "英语", role: "科任老师", permissions: ["查看本班数据", "布置作业"] },
      { id: "t7", name: "小刘", subject: "实习", role: "助教", permissions: ["仅查看", "协助批改"] },
    ],
    students: generateStudents(3, 36),
  },
  {
    id: "c5",
    name: "初一(5)班",
    myRole: "科任",
    studentCount: 36,
    maleCount: 19,
    femaleCount: 17,
    tierA: 10,
    tierB: 20,
    tierC: 6,
    warningCount: 2,
    status: "正常教学",
    lastUpdate: "3天前（更新成绩数据）",
    syncStatus: "已与钉钉同步（36人全部匹配）",
    teachers: [
      { id: "t8", name: "刘老师", subject: "语文", role: "班主任", permissions: ["全部权限"] },
      { id: "t1", name: "我（张老师）", subject: "语文", role: "科任老师", permissions: ["查看本班数据", "布置作业"] },
      { id: "t9", name: "陈老师", subject: "数学", role: "科任老师", permissions: ["查看本班数据", "布置作业"] },
    ],
    students: generateStudents(5, 36),
  },
];

export const MOCK_SYNC_LOGS: MockSyncLog[] = [
  { id: "sl1", time: "2分钟前", action: "名单同步", result: "成功", detail: "36人全部匹配" },
  { id: "sl2", time: "1小时前", action: "成绩同步", result: "成功", detail: "语文月考成绩已同步" },
  { id: "sl3", time: "昨日 18:30", action: "家长信息同步", result: "部分成功", detail: "2位家长手机号未验证" },
  { id: "sl4", time: "2天前", action: "名单同步", result: "成功", detail: "36人全部匹配" },
  { id: "sl5", time: "3天前", action: "作业数据回传", result: "成功", detail: "第12周作业已回传" },
];

// ===== DB → Mock 转换工具函数 =====

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0;
  }
  return Math.abs(hash);
}

export function dbStudentToMockStudent(
  student: { id: string; name: string; student_number: string },
  index: number
): MockStudent {
  const h = hashString(student.name);
  const gender: "男" | "女" = h % 3 === 0 ? "女" : "男";
  const tierVal = h % 100;
  const tier: "A" | "B" | "C" = tierVal < 33 ? "A" : tierVal < 66 ? "B" : "C";
  const isWarning = tier === "C" && h % 5 === 0;

  const surnames = ["李", "王", "张", "刘", "陈"];
  const givenMale = ["明", "华", "强"];
  const givenFemale = ["芳", "静", "丽"];

  return {
    id: student.id,
    studentNumber: student.student_number,
    name: student.name,
    gender,
    tier,
    status: isWarning ? "预警" : "正常",
    birthday: `20${10 + (h % 3)}-${String((h % 12) + 1).padStart(2, "0")}-${String((h % 28) + 1).padStart(2, "0")}`,
    phone: h % 3 === 0 ? `138****${String(1000 + index).slice(-4)}` : undefined,
    parentName: `${student.name.charAt(0)}大${gender === "男" ? givenMale[h % 3] : givenFemale[h % 3]}（${h % 2 === 0 ? "父亲" : "母亲"}）`,
    parentPhone: `139****${String(5000 + index).slice(-4)}`,
    enrollDate: "2023-09",
    seatRow: Math.floor(index / 6) + 1,
    seatCol: (index % 6) + 1,
    role: index === 0 ? "班长" : index === 1 ? "学习委员" : undefined,
    tags: isWarning ? ["学业预警"] : [],
    notes: isWarning ? "需加强基础训练，建议增加课后辅导" : "",
    history: [
      { date: "2024-03-15", action: `学期初信息录入`, operator: "系统" },
    ],
  };
}

export function dbClassToMockClass(
  dbClass: { id: string; name: string; grade: string; school_level: string; student_count: number },
  dbStudents: { id: string; name: string; student_number: string }[]
): MockClassInfo {
  const students = dbStudents.map((s, i) => dbStudentToMockStudent(s, i));
  const maleCount = students.filter((s) => s.gender === "男").length;
  const femaleCount = students.filter((s) => s.gender === "女").length;
  const tierA = students.filter((s) => s.tier === "A").length;
  const tierB = students.filter((s) => s.tier === "B").length;
  const tierC = students.filter((s) => s.tier === "C").length;
  const warningCount = students.filter((s) => s.status === "预警").length;

  return {
    id: dbClass.id,
    name: dbClass.name,
    myRole: "班主任",
    studentCount: dbClass.student_count || students.length,
    maleCount,
    femaleCount,
    tierA,
    tierB,
    tierC,
    warningCount,
    status: "正常教学",
    lastUpdate: "数据库实时数据",
    syncStatus: `已录入${students.length}名学生`,
    teachers: [
      { id: "t-self", name: "我（老师）", subject: "语文", role: "班主任", permissions: ["全部权限"] },
    ],
    students,
  };
}
