// 小程序全局配置。部署到正式环境时改这里即可。

module.exports = {
  // 后端地址。已切到公网正式环境（手机真机/体验版都用这个）。
  // 本地联调时可临时改回：'http://127.0.0.1:6888/api/v1'
  apiBase: 'https://xuyue.6108.net/api/v1',

  // 产品名，显示在页面标题上
  appName: '叙阅',

  // 打印状态轮询间隔（毫秒）
  pollInterval: 2000,
  // 轮询总时长上限（毫秒），超过就停止并提示老师去打印机看看
  pollTimeout: 60000,

  // 学科选项
  subjects: [
    { value: 'chinese', label: '语文' },
    { value: 'math', label: '数学' },
    { value: 'english', label: '英语' },
    { value: 'physics', label: '物理' },
    { value: 'chemistry', label: '化学' },
    { value: 'biology', label: '生物' },
    { value: 'politics', label: '道德与法治' },
    { value: 'history', label: '历史' },
    { value: 'geography', label: '地理' },
  ],

  // 纸张规格（value 与后端 worksheet_pdf._PAGE_SPECS 保持一致）
  // 16 开 / 8 开是国内学校印试卷最常用的两种。
  // columns = 该纸张的默认栏数；canDouble = 是否够宽能排双栏
  // （与后端 MIN_COLUMN_W 规则对应：每栏至少 200pt 才允许分栏）
  paperSizes: [
    { value: 'a4', label: 'A4（210×297mm）', columns: 1, canDouble: true },
    { value: 'a3', label: 'A3（297×420mm）', columns: 2, canDouble: true },
    { value: '16k', label: '16开（185×260mm）', columns: 1, canDouble: true },
    { value: '8k', label: '8开（260×370mm）', columns: 2, canDouble: true },
    { value: 'b5', label: 'B5（176×250mm）', columns: 1, canDouble: false },
    { value: 'letter', label: 'Letter（216×279mm）', columns: 1, canDouble: true },
  ],

  // 排版方式。auto = 按纸张自动（大纸默认双栏，和小字号试卷一样）
  layoutModes: [
    { value: 'auto', label: '自动（按纸张）' },
    { value: 'single', label: '单栏' },
    { value: 'double', label: '双栏' },
  ],

  // 学期（与网页版智能组卷一致）
  terms: ['上学期', '下学期'],

  // 难度（与网页版智能组卷一致）
  difficulties: ['简单', '中等', '偏难'],

  // 题型（value 与后端 type 字段一致）
  questionTypes: [
    { value: 'choice', label: '选择题' },
    { value: 'fill', label: '填空题' },
    { value: 'judge', label: '判断题' },
    { value: 'calculation', label: '计算题' },
    { value: 'short_answer', label: '简答题' },
    { value: 'application', label: '解答题' },
    { value: 'reading', label: '阅读理解' },
    { value: 'essay', label: '作文' },
  ],

  // 年级选项
  grades: [
    { value: 'grade1', label: '一年级' },
    { value: 'grade2', label: '二年级' },
    { value: 'grade3', label: '三年级' },
    { value: 'grade4', label: '四年级' },
    { value: 'grade5', label: '五年级' },
    { value: 'grade6', label: '六年级' },
    { value: 'junior1', label: '七年级' },
    { value: 'junior2', label: '八年级' },
    { value: 'junior3', label: '九年级' },
    { value: 'senior1', label: '高一' },
    { value: 'senior2', label: '高二' },
    { value: 'senior3', label: '高三' },
  ],
}
