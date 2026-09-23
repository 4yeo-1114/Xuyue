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
          reject(new Error('登录已过期，请重新登录'))
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
          reject(new Error('登录已过期，请重新登录'))
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
          reject(new Error('登录已过期，请重新登录'))
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
          reject(new Error('登录已过期，请重新登录'))
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
          reject(new Error('登录已过期，请重新登录'))
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
  uploadMaterial: uploadMaterial,
  uploadHomeStandard: uploadHomeStandard,
  gradeHomeQuick: gradeHomeQuick,
  getGradeHome: getGradeHome,
  listGradeHomeRecent: listGradeHomeRecent,
  deleteGradeHome: deleteGradeHome,
  downloadWorksheet: downloadWorksheet,
  previewPdf: previewPdf,
  resolveFileUrl: resolveFileUrl,
}
