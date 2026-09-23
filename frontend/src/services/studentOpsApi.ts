import { API_PREFIX, API_BASE_URL } from "@/config/api";
import { getAuthToken, request } from "@/services/api";

/* ──────────────────────────────────────────────────────────────────────────
 * 学生端运营域（C 域）API — 争章 / 学分银行 / 兑换 / 校外实践 / 校园生活
 * 复用 @/services/api 导出的 request<T>()（fetch + Bearer + 解包 data）
 * ────────────────────────────────────────────────────────────────────────── */

/**
 * 拼接查询参数（跳过 undefined / null / 空串 / "__all" 哨兵）。
 * "__all" 用于 Select 的“全部”选项 —— radix Select 不允许空字符串作为 item value，
 * 因此用非空哨兵值，并在拼查询参数时剔除，等价于“不过滤”。
 */
function buildQuery(params: Record<string, unknown>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== "__all") {
      qs.append(k, String(v));
    }
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

/* ── 通用类型 ── */

/** 学生端运营分页响应（后端返回 items/total/page/pageSize） */
export interface SOPaginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface SOFailure {
  studentId: string;
  studentName?: string;
  reason: string;
}

/* ── 争章 ── */

export interface BadgeDefinition {
  id: string;
  name: string;
  description?: string | null;
  badgeType: string;
  category: string;
  iconUrl?: string | null;
  pointsAwarded: number;
  minGrade?: string | null;
  maxGrade?: string | null;
  isActive: boolean;
  sortOrder: number;
  createdAt?: string;
}

export interface BadgeDefinitionInput {
  name: string;
  description?: string | null;
  badgeType: string;
  category: string;
  iconUrl?: string | null;
  pointsAwarded: number;
  minGrade?: string | null;
  maxGrade?: string | null;
  isActive?: boolean;
  sortOrder?: number;
}

export interface BadgeAward {
  id: string;
  studentId: string;
  studentName?: string;
  badgeDefinitionId: string;
  badgeDefinitionName?: string;
  classId: string;
  awardedBy?: string;
  awardDate: string;
  reason?: string | null;
  creditTransactionId?: string | null;
  createdAt?: string;
}

export interface AwardResult {
  id: string;
  studentId: string;
  studentName: string;
  badgeDefinitionName: string;
  pointsEarned: number;
  awardDate: string;
}

export interface AwardBadgesResponse {
  successCount: number;
  failCount: number;
  failures: SOFailure[];
  awards: AwardResult[];
}

export function listBadgeDefinitions(
  params: {
    badgeType?: string;
    category?: string;
    isActive?: boolean | string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<BadgeDefinition>> {
  return request<SOPaginated<BadgeDefinition>>(
    `/student-ops/badge-definitions${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function createBadgeDefinition(
  body: BadgeDefinitionInput,
): Promise<BadgeDefinition> {
  return request<BadgeDefinition>("/student-ops/badge-definitions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateBadgeDefinition(
  id: string,
  body: Partial<BadgeDefinitionInput>,
): Promise<BadgeDefinition> {
  return request<BadgeDefinition>(`/student-ops/badge-definitions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteBadgeDefinition(
  id: string,
): Promise<{ id: string; isActive: boolean }> {
  return request<{ id: string; isActive: boolean }>(
    `/student-ops/badge-definitions/${id}`,
    {
      method: "DELETE",
    },
  );
}

export function awardBadges(body: {
  studentIds: string[];
  badgeDefinitionId: string;
  awardDate: string;
  reason?: string | null;
}): Promise<AwardBadgesResponse> {
  return request<AwardBadgesResponse>("/student-ops/badge-awards", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listBadgeAwards(
  params: {
    classId?: string;
    studentId?: string;
    badgeDefinitionId?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<BadgeAward>> {
  return request<SOPaginated<BadgeAward>>(
    `/student-ops/badge-awards${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function revokeBadgeAward(
  id: string,
): Promise<{ id: string; deleted: boolean }> {
  return request<{ id: string; deleted: boolean }>(
    `/student-ops/badge-awards/${id}`,
    {
      method: "DELETE",
    },
  );
}

/* ── 学分银行 ── */

export interface CreditAccount {
  accountId: string;
  studentId: string;
  studentName?: string;
  classId?: string;
  className?: string;
  balance: number;
  totalEarned: number;
  totalSpent: number;
  updatedAt?: string;
}

export interface CreditTransaction {
  id: string;
  studentId: string;
  studentName?: string;
  className?: string;
  amount: number;
  transactionType: string;
  balanceAfter: number;
  sourceType?: string | null;
  sourceId?: string | null;
  description?: string | null;
  operatorName?: string;
  createdAt?: string;
}

export interface ManualCreditResult {
  id: string;
  studentId: string;
  amount: number;
  transactionType: string;
  balanceAfter: number;
  balance: number;
  description?: string;
  createdAt?: string;
}

export interface CreditReportSummary {
  totalStudents: number;
  totalBalance: number;
  avgBalance: number;
  totalEarnedPeriod: number;
  totalSpentPeriod: number;
}

export interface CreditReportByClass {
  classId: string;
  className: string;
  studentCount: number;
  totalBalance: number;
  avgBalance: number;
}

export interface CreditReportByType {
  type: string;
  totalAmount: number;
  count: number;
}

export interface CreditReport {
  summary: CreditReportSummary;
  byClass: CreditReportByClass[];
  byType: CreditReportByType[];
}

export interface ReconciliationItem {
  studentId: string;
  accountExists: boolean;
  status: "ok" | "mismatch" | "no_account";
  sumAmount: number;
  accountBalance: number;
  lastBalanceAfter?: number | null;
}

export function listCreditAccounts(
  params: {
    classId?: string;
    sortBy?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<CreditAccount>> {
  return request<SOPaginated<CreditAccount>>(
    `/student-ops/credit-accounts${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function listCreditTransactions(
  params: {
    studentId?: string;
    classId?: string;
    transactionType?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<CreditTransaction>> {
  return request<SOPaginated<CreditTransaction>>(
    `/student-ops/credit-transactions${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function manualCredit(body: {
  studentId: string;
  amount: number;
  description: string;
}): Promise<ManualCreditResult> {
  return request<ManualCreditResult>(
    "/student-ops/credit-transactions/manual",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function creditReport(
  params: {
    classId?: string;
    grade?: string;
    startDate?: string;
    endDate?: string;
    groupBy?: string;
  } = {},
): Promise<CreditReport> {
  return request<CreditReport>(
    `/student-ops/credit-report${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function creditReconciliation(
  params: {
    studentId?: string;
    classId?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<ReconciliationItem>> {
  return request<SOPaginated<ReconciliationItem>>(
    `/student-ops/credit-reconciliation${buildQuery(params as Record<string, unknown>)}`,
  );
}

/* ── 兑换管理 ── */

export interface RewardProduct {
  id: string;
  name: string;
  description?: string | null;
  imageUrl?: string | null;
  productType: string;
  pointsRequired: number;
  stock: number;
  stockWarning: number;
  isActive: boolean;
  exchangeLimitPerStudent: number;
  sortOrder: number;
  createdAt?: string;
}

export interface RewardProductInput {
  name: string;
  description?: string | null;
  imageUrl?: string | null;
  productType: string;
  pointsRequired: number;
  stock?: number;
  stockWarning?: number;
  isActive?: boolean;
  exchangeLimitPerStudent?: number;
  sortOrder?: number;
}

export interface Redemption {
  id: string;
  studentId: string;
  studentName?: string;
  productId: string;
  productName?: string;
  classId: string;
  pointsSpent: number;
  status: string;
  operatorId?: string;
  approverId?: string | null;
  approvedAt?: string;
  deliveredAt?: string;
  notes?: string | null;
  creditTransactionId?: string | null;
  balanceAfter?: number | null;
  createdAt?: string;
}

export interface CreateRedemptionResult {
  id: string;
  studentId: string;
  studentName: string;
  productName: string;
  pointsSpent: number;
  balanceAfter: number;
  status: string;
}

export function listRewardProducts(
  params: {
    productType?: string;
    isActive?: boolean | string;
    keyword?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<RewardProduct>> {
  return request<SOPaginated<RewardProduct>>(
    `/student-ops/reward-products${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function createRewardProduct(
  body: RewardProductInput,
): Promise<RewardProduct> {
  return request<RewardProduct>("/student-ops/reward-products", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateRewardProduct(
  id: string,
  body: Partial<RewardProductInput>,
): Promise<RewardProduct> {
  return request<RewardProduct>(`/student-ops/reward-products/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteRewardProduct(
  id: string,
): Promise<{ id: string; isActive: boolean }> {
  return request<{ id: string; isActive: boolean }>(
    `/student-ops/reward-products/${id}`,
    {
      method: "DELETE",
    },
  );
}

export function createRedemption(body: {
  studentId: string;
  productId: string;
}): Promise<CreateRedemptionResult> {
  return request<CreateRedemptionResult>("/student-ops/redemptions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listRedemptions(
  params: {
    classId?: string;
    studentId?: string;
    productId?: string;
    status?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<Redemption>> {
  return request<SOPaginated<Redemption>>(
    `/student-ops/redemptions${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function updateRedemptionStatus(
  id: string,
  body: { status: string; notes?: string | null },
): Promise<Redemption> {
  return request<Redemption>(`/student-ops/redemptions/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/* ── 激励终端报表 ── */

export interface StockStatsItem {
  id: string;
  name: string;
  productType: string;
  stock: number;
  stockWarning: number;
  pointsRequired: number;
  isActive: boolean;
  lowStock: boolean;
  outOfStock: boolean;
}

export interface ReportTrendPoint {
  period: string;
  count: number;
  pointsSpent: number;
}

export interface StockStats {
  summary: {
    totalProducts: number;
    physicalProducts: number;
    lowStockCount: number;
    outOfStockCount: number;
    totalStock: number;
  };
  items: StockStatsItem[];
  lowStockItems: StockStatsItem[];
  trend: ReportTrendPoint[];
}

export function stockStats(): Promise<StockStats> {
  return request<StockStats>("/student-ops/reward-products/stock-stats");
}

export interface RedemptionStatusDist {
  status: string;
  count: number;
}

export interface RedemptionTopProduct {
  productId: string;
  productName: string;
  count: number;
  pointsSpent: number;
}

export interface RedemptionReport {
  summary: {
    totalRedemptions: number;
    totalPointsSpent: number;
    activeCount: number;
    cancelledCount: number;
  };
  statusDistribution: RedemptionStatusDist[];
  topProducts: RedemptionTopProduct[];
  trend: ReportTrendPoint[];
}

export function redemptionReport(
  params: {
    startDate?: string;
    endDate?: string;
    classId?: string;
    groupBy?: string;
  } = {},
): Promise<RedemptionReport> {
  return request<RedemptionReport>(
    `/student-ops/redemptions/report${buildQuery(params as Record<string, unknown>)}`,
  );
}

/* ── 校外实践 ── */

export interface EvidenceImage {
  url: string;
  thumbUrl?: string;
  uploadAt?: string;
}

export interface PracticeRecord {
  id: string;
  studentId: string;
  studentName?: string;
  classId: string;
  practiceType: string;
  title: string;
  description?: string | null;
  practiceDate: string;
  durationHours?: number | null;
  location?: string | null;
  evidenceImages: EvidenceImage[];
  status: string;
  reviewerId?: string | null;
  reviewComment?: string | null;
  reviewedAt?: string;
  creditTransactionId?: string | null;
  recordedBy?: string;
  createdAt?: string;
}

export interface PracticeInput {
  studentId: string;
  practiceType: string;
  title: string;
  description?: string | null;
  practiceDate: string;
  durationHours?: number | null;
  location?: string | null;
  evidenceImages?: EvidenceImage[] | null;
}

export function createPracticeRecord(
  body: PracticeInput,
): Promise<PracticeRecord> {
  return request<PracticeRecord>("/student-ops/practice-records", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listPracticeRecords(
  params: {
    classId?: string;
    studentId?: string;
    practiceType?: string;
    status?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<PracticeRecord>> {
  return request<SOPaginated<PracticeRecord>>(
    `/student-ops/practice-records${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function updatePracticeRecord(
  id: string,
  body: Partial<PracticeInput>,
): Promise<PracticeRecord> {
  return request<PracticeRecord>(`/student-ops/practice-records/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deletePracticeRecord(
  id: string,
): Promise<{ id: string; deleted: boolean }> {
  return request<{ id: string; deleted: boolean }>(
    `/student-ops/practice-records/${id}`,
    {
      method: "DELETE",
    },
  );
}

export function reviewPracticeRecord(
  id: string,
  body: { status: "approved" | "rejected"; reviewComment?: string | null },
): Promise<PracticeRecord> {
  return request<PracticeRecord>(`/student-ops/practice-records/${id}/review`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/* ── 文件上传 ── */

export interface UploadEvidenceResult {
  url: string;
  thumbUrl?: string;
  fileName: string;
}

/** 上传实践佐证图片（multipart/form-data），返回相对路径 */
export async function uploadEvidence(
  file: File,
): Promise<UploadEvidenceResult> {
  const formData = new FormData();
  formData.append("file", file);

  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_PREFIX}/student-ops/upload-evidence`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "上传失败");
  }
  const json = await res.json();
  return json.data as UploadEvidenceResult;
}

export interface FileUrlResult {
  downloadUrl: string;
}

/** 获取带 download ticket 的临时直链 */
export async function getFileUrl(path: string): Promise<FileUrlResult> {
  return request<FileUrlResult>(
    `/student-ops/get-file-url${buildQuery({ path })}`,
  );
}

/** 将相对路径拼成可访问的完整 URL（开发环境 API_BASE_URL 为 http://localhost:6888） */
export function resolveFileUrl(downloadUrl: string): string {
  if (!downloadUrl) return "";
  if (/^https?:\/\//.test(downloadUrl)) return downloadUrl;
  return `${API_BASE_URL}${downloadUrl}`;
}

/* ── 校园生活：社团 ── */

export interface CampusClub {
  id: string;
  name: string;
  description?: string | null;
  teacherId?: string | null;
  teacherName?: string;
  maxMembers: number;
  isActive: boolean;
  createdAt?: string;
}

export interface ClubEnrollment {
  id: string;
  studentId: string;
  studentName?: string;
  clubId: string;
  classId: string;
  status: string;
  enrolledAt?: string;
  leftAt?: string | null;
  recordedBy?: string;
  createdAt?: string;
}

export interface ClubAttendance {
  id: string;
  studentId: string;
  studentName?: string;
  clubId: string;
  classId: string;
  sessionDate: string;
  attendStatus: string;
  remarks?: string | null;
  recordedBy?: string;
  createdAt?: string;
}

export function listClubs(
  params: {
    keyword?: string;
    isActive?: boolean | string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<CampusClub>> {
  return request<SOPaginated<CampusClub>>(
    `/student-ops/clubs${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function createClub(body: Partial<CampusClub>): Promise<CampusClub> {
  return request<CampusClub>("/student-ops/clubs", {
    method: "POST",
    body: JSON.stringify({
      name: body.name,
      description: body.description,
      teacherId: body.teacherId,
      maxMembers: body.maxMembers,
      isActive: body.isActive,
    }),
  });
}

export function updateClub(
  id: string,
  body: Partial<CampusClub>,
): Promise<CampusClub> {
  return request<CampusClub>(`/student-ops/clubs/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: body.name,
      description: body.description,
      teacherId: body.teacherId,
      maxMembers: body.maxMembers,
      isActive: body.isActive,
    }),
  });
}

export function deleteClub(
  id: string,
): Promise<{ id: string; isActive: boolean }> {
  return request<{ id: string; isActive: boolean }>(
    `/student-ops/clubs/${id}`,
    {
      method: "DELETE",
    },
  );
}

export function listClubEnrollments(
  clubId: string,
  params: { status?: string; page?: number; pageSize?: number } = {},
): Promise<SOPaginated<ClubEnrollment>> {
  return request<SOPaginated<ClubEnrollment>>(
    `/student-ops/clubs/${clubId}/enrollments${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function batchClubEnrollments(body: {
  clubId: string;
  studentIds: string[];
  enrolledAt?: string;
}): Promise<{
  successCount: number;
  failCount: number;
  failures: SOFailure[];
}> {
  return request<{
    successCount: number;
    failCount: number;
    failures: SOFailure[];
  }>("/student-ops/club-enrollments", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateClubEnrollment(
  id: string,
  body: { status: "enrolled" | "left" },
): Promise<ClubEnrollment> {
  return request<ClubEnrollment>(`/student-ops/club-enrollments/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function batchClubAttendance(body: {
  clubId: string;
  sessionDate: string;
  records: {
    studentId: string;
    attendStatus: string;
    remarks?: string | null;
  }[];
}): Promise<{
  successCount: number;
  failCount: number;
  failures: SOFailure[];
}> {
  return request<{
    successCount: number;
    failCount: number;
    failures: SOFailure[];
  }>("/student-ops/club-attendance", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listClubAttendance(
  params: {
    clubId?: string;
    sessionDate?: string;
    classId?: string;
    studentId?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<ClubAttendance>> {
  return request<SOPaginated<ClubAttendance>>(
    `/student-ops/club-attendance${buildQuery(params as Record<string, unknown>)}`,
  );
}

/* ── 校园生活：图书借阅 ── */

export interface BookBorrow {
  id: string;
  studentId: string;
  studentName?: string;
  classId: string;
  bookTitle: string;
  bookIsbn?: string | null;
  bookAuthor?: string | null;
  borrowedAt: string;
  dueAt: string;
  returnedAt?: string | null;
  status: string;
  recordedBy?: string;
  notes?: string | null;
  createdAt?: string;
}

export function listBookBorrows(
  params: {
    classId?: string;
    studentId?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<BookBorrow>> {
  return request<SOPaginated<BookBorrow>>(
    `/student-ops/book-borrows${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function createBookBorrow(body: {
  studentId: string;
  bookTitle: string;
  bookIsbn?: string | null;
  bookAuthor?: string | null;
  borrowedAt?: string;
  dueAt: string;
  notes?: string | null;
}): Promise<BookBorrow> {
  return request<BookBorrow>("/student-ops/book-borrows", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function returnBookBorrow(
  id: string,
  body: { returnedAt?: string; notes?: string | null },
): Promise<BookBorrow> {
  return request<BookBorrow>(`/student-ops/book-borrows/${id}/return`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function listOverdueBookBorrows(
  params: {
    classId?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<BookBorrow>> {
  return request<SOPaginated<BookBorrow>>(
    `/student-ops/book-borrows/overdue${buildQuery(params as Record<string, unknown>)}`,
  );
}

/* ── 校园生活：阅读打卡 ── */

export interface ReadingRecord {
  id: string;
  studentId: string;
  studentName?: string;
  classId: string;
  bookTitle: string;
  pagesRead: number;
  readingMinutes: number;
  readingDate: string;
  recordedBy?: string;
  createdAt?: string;
}

export interface ReadingLeaderboardItem {
  rank: number;
  studentId: string;
  studentName: string;
  className: string;
  totalPages: number;
  totalMinutes: number;
  booksCount: number;
}

export interface ReadingLeaderboard {
  period: string;
  startDate: string;
  endDate: string;
  leaderboard: ReadingLeaderboardItem[];
}

export function listReadingRecords(
  params: {
    classId?: string;
    studentId?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<ReadingRecord>> {
  return request<SOPaginated<ReadingRecord>>(
    `/student-ops/reading-records${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function createReadingRecord(body: {
  studentId: string;
  bookTitle: string;
  pagesRead: number;
  readingMinutes: number;
  readingDate: string;
}): Promise<ReadingRecord> {
  return request<ReadingRecord>("/student-ops/reading-records", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function batchReadingRecords(body: {
  records: {
    studentId: string;
    bookTitle: string;
    pagesRead?: number;
    readingMinutes?: number;
    readingDate: string;
  }[];
}): Promise<{
  successCount: number;
  failCount: number;
  failures: SOFailure[];
}> {
  return request<{
    successCount: number;
    failCount: number;
    failures: SOFailure[];
  }>("/student-ops/reading-records/batch", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function readingLeaderboard(
  params: {
    period?: string;
    classId?: string;
    limit?: number;
  } = {},
): Promise<ReadingLeaderboard> {
  return request<ReadingLeaderboard>(
    `/student-ops/reading-leaderboard${buildQuery(params as Record<string, unknown>)}`,
  );
}

/* ── 校园生活：晨午检 ── */

export interface HealthCheck {
  id: string;
  studentId: string;
  studentName?: string;
  classId: string;
  checkType: string;
  checkDate: string;
  temperature?: number | null;
  healthStatus: string;
  symptoms?: string | null;
  isAlert: boolean;
  handledBy?: string | null;
  handleNotes?: string | null;
  recordedBy?: string;
  createdAt?: string;
}

export interface HealthAlert extends HealthCheck {
  consecutiveAlertDays: number;
  isHandled: boolean;
}

export function listHealthChecks(
  params: {
    classId?: string;
    studentId?: string;
    checkType?: string;
    checkDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<HealthCheck>> {
  return request<SOPaginated<HealthCheck>>(
    `/student-ops/health-checks${buildQuery(params as Record<string, unknown>)}`,
  );
}

export function batchHealthChecks(body: {
  classId: string;
  checkType: string;
  checkDate: string;
  records: {
    studentId: string;
    temperature?: number | null;
    healthStatus?: string;
    symptoms?: string | null;
  }[];
}): Promise<{
  successCount: number;
  failCount: number;
  failures: SOFailure[];
}> {
  return request<{
    successCount: number;
    failCount: number;
    failures: SOFailure[];
  }>("/student-ops/health-checks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateHealthCheck(
  id: string,
  body: Partial<{
    temperature: number;
    healthStatus: string;
    symptoms: string;
    handledBy: string;
    handleNotes: string;
    isAlert: boolean;
  }>,
): Promise<HealthCheck> {
  return request<HealthCheck>(`/student-ops/health-checks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function listHealthAlerts(
  params: {
    classId?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<HealthAlert>> {
  return request<SOPaginated<HealthAlert>>(
    `/student-ops/health-alerts${buildQuery(params as Record<string, unknown>)}`,
  );
}

/* ── 校园生活：晨午检请假/出勤 ── */

export interface AttendanceRecord {
  id: string;
  studentId: string;
  studentName?: string;
  classId: string;
  date: string;
  checkType: string;
  status: string;
  reason?: string | null;
  recordedBy?: string;
  createdAt?: string;
}

export function batchAttendance(body: {
  classId: string;
  date: string;
  checkType: string;
  records: { studentId: string; status: string; reason?: string | null }[];
}): Promise<{
  successCount: number;
  failCount: number;
  failures: SOFailure[];
}> {
  return request<{
    successCount: number;
    failCount: number;
    failures: SOFailure[];
  }>("/student-ops/attendance", { method: "POST", body: JSON.stringify(body) });
}

export function listAttendance(
  params: {
    classId?: string;
    studentId?: string;
    checkType?: string;
    date?: string;
    status?: string;
    startDate?: string;
    endDate?: string;
    page?: number;
    pageSize?: number;
  } = {},
): Promise<SOPaginated<AttendanceRecord>> {
  return request<SOPaginated<AttendanceRecord>>(
    `/student-ops/attendance${buildQuery(params as Record<string, unknown>)}`,
  );
}

export interface AttendanceDailyStat {
  date: string;
  present: number;
  leave: number;
  late: number;
  absent: number;
  total: number;
}

export interface AttendanceStudentStat {
  studentId: string;
  studentName: string;
  present: number;
  leave: number;
  late: number;
  absent: number;
  total: number;
}

export interface AttendanceStats {
  classId: string;
  className: string;
  from: string;
  to: string;
  summary: {
    expected: number;
    present: number;
    leave: number;
    late: number;
    absent: number;
    anomalyRate: number;
  };
  byDate: AttendanceDailyStat[];
  byStudent: AttendanceStudentStat[];
}

export function attendanceStats(params: {
  classId: string;
  from?: string;
  to?: string;
  checkType?: string;
}): Promise<AttendanceStats> {
  return request<AttendanceStats>(
    `/student-ops/attendance/stats${buildQuery(params as Record<string, unknown>)}`,
  );
}
