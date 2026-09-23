"""C 域业务常量（可配置项集中管理）"""

# 实践审核通过奖励积分
PRACTICE_REWARD_POINTS = 50
# 社团全勤（学期）奖励积分
CLUB_FULL_ATTENDANCE_POINTS = 30
# 阅读月榜前 10 奖励积分
READING_TOP10_POINTS = 20
# 健康异常连续 3 天：仅留痕，不加分
HEALTH_ALERT_POINTS = 0

# 分页
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# 批量颁章上限
BATCH_AWARD_LIMIT = 200
# 单条实践记录图片上限
EVIDENCE_MAX_IMAGES = 9
# 单张图片大小上限
UPLOAD_MAX_BYTES = 10 * 1024 * 1024
# 允许上传的图片扩展名
UPLOAD_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".heic"}
