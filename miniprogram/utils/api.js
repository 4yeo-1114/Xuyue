// 后端接口封装。所有网络请求都走这里，便于统一处理登录态与报错。

const config = require('./config')

const TOKEN_KEY = 'xuyue_token'
const USER_KEY = 'xuyue_user'

function getToken() {
  return wx.getStorageSync(TOKEN_KEY) || ''
}

function setSession(token, user) {
  wx.setStorageSync(TOKEN_KEY, token || '')
  if (user) wx.setStorageSync(USER_KEY, user)
}

function getUser() {
  return wx.getStorageSync(USER_KEY) || null
}

function clearSession() {
  wx.removeStorageSync(TOKEN_KEY)
  wx.removeStorageSync(USER_KEY)
}

// 统一请求。返回 Promise，失败时 reject 一个带 message 的 Error。
function request(method, path, data, options) {
  options = options || {}
  return new Promise(function (resolve, reject) {
    const header = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) header.Authorization = 'Bearer ' + token

    wx.request({
      url: config.apiBase + path,
      method: method,
      data: data,
      header: header,
      timeout: options.timeout || 20000,
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else if (res.statusCode === 401) {
          clearSession()
          // 密码错误/验证码等具体原因要透出，只有「未登录/失效」才提示重新登录
          let d401 = ''
          try {
            const body401 = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
            d401 = (body401 && body401.detail) || ''
          } catch (e) {}
          const generic = !d401 || d401 === '未登录' || d401 === '登录已过期或无效'
          reject(new Error(generic ? '登录已过期，请重新登录' : d401))
        } else {
          const detail = (res.data && res.data.detail) || ''
          reject(new Error(detail || ('请求失败（' + res.statusCode + '）')))
        }
      },
      fail: function (err) {
        reject(new Error('网络异常：' + (err.errMsg || '请检查网络')))
      },
    })
  })
}

// ─── 登录 ───
function login(email, password) {
  return request('POST', '/auth/login', { email: email, password: password }).then(
    function (data) {
      const token = data.access_token || data.token
      setSession(token, data.user || null)
      return data
    }
  )
}

function logout() {
  clearSession()
}

// 取当前登录用户信息（用于预填「布置老师」）
function getMe() {
  return request('GET', '/auth/me').then(function (data) {
    // 有的接口把用户包在 data 里，这里都兼容
    const user = data && data.data ? data.data : data
    if (user) wx.setStorageSync(USER_KEY, user)
    return user
  })
}

// ─── 注册 ───
// 签发邮箱验证码（注册用途）
function sendEmailCode(target) {
  return request('POST', '/auth/send-code', { target: target, channel: 'email', purpose: 'register' })
}

// 注册并自动登录（后端返回 access_token，与网页版同一接口）
function register(payload) {
  return request('POST', '/auth/register', payload).then(function (data) {
    const token = data.access_token || data.token
    setSession(token, data.user || null)
    return data
  })
}

// ─── 打印任务 ───
// 布置作业：生成作业纸并送进打印队列
function createPrintJob(payload) {
  return request('POST', '/print-jobs', payload)
}

// 查任务状态（结果页轮询用）
function getPrintJob(jobId) {
  return request('GET', '/print-jobs/' + jobId)
}

// 我的打印记录
function listPrintJobs(limit) {
  return request('GET', '/print-jobs?limit=' + (limit || 20))
}

// 送出打印（老师在预览页确认后才调）。可选临时改份数。
function printJob(jobId, copies) {
  const body = copies ? { copies: copies } : {}
  return request('POST', '/print-jobs/' + jobId + '/print', body)
}

// 删除一份作业（草稿，或还没被打印机取走的）
function cancelPrintJob(jobId) {
  return request('DELETE', '/print-jobs/' + jobId)
}

// ─── AI 出题 ───
// 与网页版「智能组卷」同一个接口
function generateQuestionsByAI(body) {
  return request('POST', '/exams/ai-generate', body, { timeout: 180000 }).then(function (res) {
    // 后端包了一层 ApiResponse，题目在 data 里
    if (Array.isArray(res)) return res
    return (res && res.data) || []
  })
}

// ─── 试卷库（网页版「智能组卷」保存的试卷，两端共用同一份） ───
function listExamPapers() {
  return request('GET', '/exams/papers').then(function (res) {
    // 同样包了 ApiResponse，试卷数组在 data 里
    if (Array.isArray(res)) return res
    return (res && res.data) || []
  })
}

// ─── 上传题目材料 ───
// filePath: wx.chooseMedia / chooseMessageFile 拿到的临时路径
// fileName: 原始文件名（用来判断格式，临时路径常常没有后缀）
function uploadMaterial(filePath, fileName) {
  return new Promise(function (resolve, reject) {
    const token = getToken()
    wx.uploadFile({
      url: config.apiBase + '/print-jobs/upload',
      filePath: filePath,
      name: 'file',
      formData: { filename: fileName || '' },
      header: token ? { Authorization: 'Bearer ' + token } : {},
      timeout: 120000,
      success: function (res) {
        let data = {}
        try {
          data = JSON.parse(res.data || '{}')
        } catch (e) {
          data = {}
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data)
        } else if (res.statusCode === 401) {
          clearSession()
          // 密码错误/验证码等具体原因要透出，只有「未登录/失效」才提示重新登录
          let d401 = ''
          try {
            const body401 = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
            d401 = (body401 && body401.detail) || ''
          } catch (e) {}
          const generic = !d401 || d401 === '未登录' || d401 === '登录已过期或无效'
          reject(new Error(generic ? '登录已过期，请重新登录' : d401))
        } else {
          reject(new Error(data.detail || '上传失败（' + res.statusCode + '）'))
        }
      },
      fail: function (err) {
        reject(new Error('上传失败：' + (err.errMsg || '请检查网络')))
      },
    })
  })
}

// ─── 批改作业（首页图片批改）───
// 上传单张试卷图片，后台启动批改，返回 job_id
function uploadHomeStandard(filePath) {
  return new Promise(function (resolve, reject) {
    const token = getToken()
    wx.uploadFile({
      url: config.apiBase + '/grading/home/standard',
      filePath: filePath,
      name: 'file',
      header: token ? { Authorization: 'Bearer ' + token } : {},
      timeout: 120000,
      success: function (res) {
        let data = {}
        try {
          data = JSON.parse(res.data || '{}')
        } catch (e) {
          data = {}
        }
        if (res.statusCode >= 200 && res.statusCode < 300 && data.standard_id) {
          resolve(data.standard_id)
        } else if (res.statusCode === 401) {
          clearSession()
          // 密码错误/验证码等具体原因要透出，只有「未登录/失效」才提示重新登录
          let d401 = ''
          try {
            const body401 = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
            d401 = (body401 && body401.detail) || ''
          } catch (e) {}
          const generic = !d401 || d401 === '未登录' || d401 === '登录已过期或无效'
          reject(new Error(generic ? '登录已过期，请重新登录' : d401))
        } else {
          reject(new Error(data.detail || '答案卷上传失败（' + res.statusCode + '）'))
        }
      },
      fail: function (err) {
        reject(new Error('答案卷上传失败：' + (err.errMsg || '请检查网络')))
      },
    })
  })
}

function gradeHomeQuick(filePath, standardId) {
  return new Promise(function (resolve, reject) {
    const token = getToken()
    const formData = { anonymous: 'false' }
    if (standardId) formData.standard_id = standardId
    wx.uploadFile({
      url: config.apiBase + '/grading/home/quick',
      filePath: filePath,
      name: 'file',
      formData: formData,
      header: token ? { Authorization: 'Bearer ' + token } : {},
      timeout: 120000,
      success: function (res) {
        let data = {}
        try {
          data = JSON.parse(res.data || '{}')
        } catch (e) {
          data = {}
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data)
        } else if (res.statusCode === 401) {
          clearSession()
          // 密码错误/验证码等具体原因要透出，只有「未登录/失效」才提示重新登录
          let d401 = ''
          try {
            const body401 = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
            d401 = (body401 && body401.detail) || ''
          } catch (e) {}
          const generic = !d401 || d401 === '未登录' || d401 === '登录已过期或无效'
          reject(new Error(generic ? '登录已过期，请重新登录' : d401))
        } else {
          reject(new Error(data.detail || '上传失败（' + res.statusCode + '）'))
        }
      },
      fail: function (err) {
        reject(new Error('上传失败：' + (err.errMsg || '请检查网络')))
      },
    })
  })
}

// 查批改任务详情（结果页轮询用）
function getGradeHome(jobId) {
  return request('GET', '/grading/home/' + jobId)
}

// 最近批改记录（留痕列表）
function listGradeHomeRecent() {
  return request('GET', '/grading/home/recent')
}

// 删除一条批改记录
function deleteGradeHome(jobId) {
  return request('DELETE', '/grading/home/' + jobId)
}

// 举一反三：为该作业的错题生成 AI 变式题（含题干/答案/解析）。重 LLM，超时放宽。
// 返回 {ok, from_cache, items:[{from_key,from_title,orig_result,question,answer,analysis,...}], ...}
function generateHomeVariants(jobId, body) {
  return request('POST', '/grading/home/' + jobId + '/variants', body || {}, { timeout: 300000 })
}

// 把题目存成试卷（与网页版「智能组卷」同一份试卷库，可一键布置）
function saveExamPaper(title, subject, questions) {
  return request('POST', '/exams/papers', {
    title: title,
    subject: subject,
    questions: questions,
  }).then(unwrap)
}

// 下载作业纸 PDF 到本地临时文件，返回临时路径（用于预览）
function downloadWorksheet(jobId) {
  return new Promise(function (resolve, reject) {
    const token = getToken()
    wx.downloadFile({
      url: config.apiBase + '/print-jobs/' + jobId + '/pdf',
      header: token ? { Authorization: 'Bearer ' + token } : {},
      timeout: 60000,
      success: function (res) {
        if (res.statusCode === 200) {
          resolve(res.tempFilePath)
        } else if (res.statusCode === 401) {
          clearSession()
          // 密码错误/验证码等具体原因要透出，只有「未登录/失效」才提示重新登录
          let d401 = ''
          try {
            const body401 = typeof res.data === 'string' ? JSON.parse(res.data) : res.data
            d401 = (body401 && body401.detail) || ''
          } catch (e) {}
          const generic = !d401 || d401 === '未登录' || d401 === '登录已过期或无效'
          reject(new Error(generic ? '登录已过期，请重新登录' : d401))
        } else {
          reject(new Error('作业纸下载失败（' + res.statusCode + '）'))
        }
      },
      fail: function (err) {
        reject(new Error('作业纸下载失败：' + (err.errMsg || '')))
      },
    })
  })
}

// 打开 PDF 预览
function previewPdf(filePath) {
  return new Promise(function (resolve, reject) {
    wx.openDocument({
      filePath: filePath,
      fileType: 'pdf',
      showMenu: true,
      success: resolve,
      fail: function (err) {
        reject(new Error('无法打开预览：' + (err.errMsg || '')))
      },
    })
  })
}

// 后端返回的图片/文件直链是相对路径（如 /api/v1/grading/home_img/xxx?ticket=yyy），
// 小程序 <image> 加载需要完整域名，这里把相对路径拼成完整 URL。
function resolveFileUrl(url) {
  if (!url || typeof url !== 'string') return url
  if (/^https?:\/\//i.test(url)) return url
  if (url.charAt(0) === '/') {
    return config.apiBase.replace(/\/api\/v1\/?$/, '') + url
  }
  return url
}

// 大部分接口包了 ApiResponse{code,message,data}，这里统一拆掉信封；
// 少数老接口（批改历史/文件夹等）直接返回业务对象，原样透传。
function unwrap(body) {
  if (body && typeof body === 'object' && !Array.isArray(body) && 'code' in body && 'data' in body) {
    return body.data
  }
  return body
}

// ─── 班级 / 学生 ───
// 我的班级列表
function listClasses() {
  return request('GET', '/classes').then(unwrap)
}

// 班级学生名单
function listStudents(classId) {
  return request('GET', '/students?class_id=' + encodeURIComponent(classId || '')).then(unwrap)
}

// 新增学生（body: class_id, name, student_number?, gender?）
function createStudent(body) {
  return request('POST', '/students', body).then(unwrap)
}

// 删除学生
function deleteStudent(studentId) {
  return request('DELETE', '/students/' + encodeURIComponent(studentId)).then(unwrap)
}

// ─── 学生分析 ───
// 某生历次成绩（exam_name/score/class_avg/created_at）
function getScoreHistory(classId, studentName, subject) {
  return request(
    'GET',
    '/student-analysis/score-history?class_id=' + encodeURIComponent(classId || '') +
      '&student_name=' + encodeURIComponent(studentName || '') +
      '&subject=' + encodeURIComponent(subject || '')
  ).then(unwrap)
}

// 某生最近一场错题（含图）
function getStudentWrongQuestions(classId, studentName, subject) {
  return request(
    'GET',
    '/student-analysis/wrong-questions/latest?class_id=' + encodeURIComponent(classId || '') +
      '&student_name=' + encodeURIComponent(studentName || '') +
      '&subject=' + encodeURIComponent(subject || '')
  ).then(unwrap)
}

// 成绩趋势预警（按学生 id）
function getTrendAlerts(studentId, classId) {
  return request(
    'GET',
    '/student-analysis/trend-alert?student_id=' + encodeURIComponent(studentId || '') +
      '&class_id=' + encodeURIComponent(classId || '')
  ).then(unwrap)
}

// 学业目标（读）
function getStudentAnalysis(classId, studentName, subject) {
  return request(
    'GET',
    '/student-analysis?class_id=' + encodeURIComponent(classId || '') +
      '&student_name=' + encodeURIComponent(studentName || '') +
      '&subject=' + encodeURIComponent(subject || '')
  ).then(unwrap)
}

// 学业目标（写：target_score / current_score）
function saveStudentAnalysis(body) {
  return request('POST', '/student-analysis', body).then(unwrap)
}

// ─── 错题本（老接口不带信封，原样透传） ───
// 文件夹错题统计：参与人数/收录题目/错误率
function getErrorBookStats(folderName) {
  return request('GET', '/grading/error-book/folders/' + encodeURIComponent(folderName) + '/stats')
}

// 文件夹错题详情：题目排行 + 学生排行
function getErrorBookDetail(folderName) {
  return request('GET', '/grading/error-book/folders/' + encodeURIComponent(folderName) + '/detail')
}

// ─── 知识图谱 ───
// units + kps（kps 按 unit_id 归组），无数据时 {units:[],kps:[],isEmpty:true}
function getKnowledgeData(subject, semester) {
  return request(
    'GET',
    '/knowledge-data?subject=' + encodeURIComponent(subject || '') +
      '&semester=' + encodeURIComponent(semester || '')
  ).then(unwrap)
}


// 初始化知识点演示数据（同网页版「学科配置」的初始化按钮），按当前登录用户落库
function seedKnowledgeData(subject, semester, units) {
  return request('POST', '/knowledge-data/seed', {
    subject: subject,
    semester: semester,
    units: units,
  }).then(unwrap)
}

// 该班级的考试文件夹（含学科/年级 meta）
function listFolders(classId) {
  return request('GET', '/grading/folders?class_id=' + encodeURIComponent(classId || ''))
}

// 轻成绩表：某文件夹每生一行
function getScoreSummary(folderName) {
  return request('GET', '/grading/folders/' + encodeURIComponent(folderName) + '/score-summary')
}

// 班级学情报告（六维能力 dims 在 data.report.analysis.capability_dimensions.dims）
function getClassReport(classId, subject) {
  return request(
    'GET',
    '/class-analysis/report?class_id=' + encodeURIComponent(classId || '') +
      '&subject=' + encodeURIComponent(subject || '')
  ).then(unwrap)
}

// 靶向提升科目列表（雷达/任务共用科目选择）
function getSubjects() {
  return request('GET', '/targeted-improvement/subjects').then(unwrap)
}

// ─── 靶向提升任务清单 ───
function listImprovementTasks(classId, subject) {
  return request(
    'GET',
    '/targeted-improvement/tasks?class_id=' + encodeURIComponent(classId || '') +
      '&subject=' + encodeURIComponent(subject || '')
  ).then(unwrap)
}

// 勾/取消任务完成
function updateImprovementTask(taskId, isDone) {
  return request('PATCH', '/targeted-improvement/tasks/' + taskId, { is_done: !!isDone }).then(unwrap)
}

// ─── 改分台账 ───
// params: days / include_voided / source / change_kind / q / page / page_size
function getCorrectionLedger(params) {
  const parts = []
  const p = params || {}
  for (const k in p) {
    if (p[k] === undefined || p[k] === null || p[k] === '') continue
    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(p[k]))
  }
  return request('GET', '/grading/correction-ledger' + (parts.length ? '?' + parts.join('&') : '')).then(unwrap)
}

// ─── 额度 ───
// 我的额度用量（total/used/available/used_pct/locked/today_pages）
function getQuota() {
  return request('GET', '/quota/me').then(unwrap)
}

// 管理员账号总览（按邮箱域名分组的用量/额度），普通账号会 403
function getAdminOverview(days) {
  return request('GET', '/admin/accounts/overview?days=' + (days || 30)).then(unwrap)
}

module.exports = {
  getToken: getToken,
  getUser: getUser,
  setSession: setSession,
  clearSession: clearSession,
  login: login,
  logout: logout,
  getMe: getMe,
  createPrintJob: createPrintJob,
  getPrintJob: getPrintJob,
  listPrintJobs: listPrintJobs,
  printJob: printJob,
  cancelPrintJob: cancelPrintJob,
  generateQuestionsByAI: generateQuestionsByAI,
  listExamPapers: listExamPapers,
  uploadMaterial: uploadMaterial,
  uploadHomeStandard: uploadHomeStandard,
  gradeHomeQuick: gradeHomeQuick,
  getGradeHome: getGradeHome,
  listGradeHomeRecent: listGradeHomeRecent,
  generateHomeVariants: generateHomeVariants,
  saveExamPaper: saveExamPaper,
  deleteGradeHome: deleteGradeHome,
  downloadWorksheet: downloadWorksheet,
  previewPdf: previewPdf,
  resolveFileUrl: resolveFileUrl,
  listClasses: listClasses,
  listStudents: listStudents,
  createStudent: createStudent,
  deleteStudent: deleteStudent,
  getScoreHistory: getScoreHistory,
  getStudentWrongQuestions: getStudentWrongQuestions,
  getTrendAlerts: getTrendAlerts,
  getStudentAnalysis: getStudentAnalysis,
  saveStudentAnalysis: saveStudentAnalysis,
  getErrorBookStats: getErrorBookStats,
  getErrorBookDetail: getErrorBookDetail,
  getKnowledgeData: getKnowledgeData,
  seedKnowledgeData: seedKnowledgeData,
  listFolders: listFolders,
  getScoreSummary: getScoreSummary,
  getClassReport: getClassReport,
  getSubjects: getSubjects,
  listImprovementTasks: listImprovementTasks,
  updateImprovementTask: updateImprovementTask,
  getCorrectionLedger: getCorrectionLedger,
  getQuota: getQuota,
  getAdminOverview: getAdminOverview,
  sendEmailCode: sendEmailCode,
  register: register,
}
