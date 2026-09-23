const api = require('../../utils/api')
const config = require('../../utils/config')

// 第 0 项是「自动」：AI 模式按题型给（选择题不留线、作文 8 行），其余模式默认 2 行
const ANSWER_LINE_OPTIONS = ['自动', '1 行', '2 行', '3 行', '4 行', '5 行']
const COPIES_OPTIONS = ['1 份', '2 份', '3 份', '5 份', '8 份', '10 份']
const COPIES_VALUES = [1, 2, 3, 5, 8, 10]

const LAST_PAYLOAD_KEY = 'xuyue_last_payload'

function defaultAiTypes() {
  return config.questionTypes.map(function (t) {
    return { value: t.value, label: t.label, count: t.value === 'choice' ? 10 : 0 }
  })
}

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

Page({
  data: {
    subjectLabels: config.subjects.map(function (s) { return s.label }),
    gradeLabels: config.grades.map(function (g) { return g.label }),
    terms: config.terms,
    difficulties: config.difficulties,
    answerLineOptions: ANSWER_LINE_OPTIONS,
    copiesOptions: COPIES_OPTIONS,
    paperLabels: config.paperSizes.map(function (p) { return p.label }),
    layoutLabels: config.layoutModes.map(function (m) { return m.label }),

    // 作业基本信息
    title: '',
    subjectIndex: 1, // 默认数学
    gradeIndex: 6,   // 默认七年级
    className: '',
    teacher: '',

    // 出题方式：ai = AI 生成；self = 自己出题；upload = 上传材料
    mode: 'ai',

    // AI 生成
    aiTermIndex: 0,
    aiDifficultyIndex: 1,
    aiTopic: '',
    aiTypes: defaultAiTypes(),

    // 自己出题
    questionCount: 10,

    // 上传材料
    uploads: [],
    uploading: false,

    // 打印设置
    answerLineIndex: 0,
    copiesIndex: 0,
    paperIndex: 0, // 默认 A4
    layoutIndex: 0, // 默认「自动（按纸张）」
    layoutHint: '',
    note: '请认真作答，保持卷面整洁。',

    generating: false,
  },

  onLoad: function () {
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
      return
    }
    this.prefillTeacher()
    this.refreshLayoutHint()
  },

  prefillTeacher: function () {
    const user = api.getUser()
    if (user && (user.name || user.username)) {
      this.setData({ teacher: user.name || user.username })
      return
    }
    const that = this
    api.getMe().then(function (me) {
      if (me && (me.name || me.username)) {
        that.setData({ teacher: me.name || me.username })
      }
    }).catch(function () {})
  },

  // ─── 基本信息 ───
  onTitleInput: function (e) { this.setData({ title: e.detail.value }) },
  onClassInput: function (e) { this.setData({ className: e.detail.value }) },
  onTeacherInput: function (e) { this.setData({ teacher: e.detail.value }) },
  onNoteInput: function (e) { this.setData({ note: e.detail.value }) },
  onSubjectChange: function (e) { this.setData({ subjectIndex: Number(e.detail.value) }) },
  onGradeChange: function (e) { this.setData({ gradeIndex: Number(e.detail.value) }) },
  onAnswerLinesChange: function (e) { this.setData({ answerLineIndex: Number(e.detail.value) }) },
  onCopiesChange: function (e) { this.setData({ copiesIndex: Number(e.detail.value) }) },
  onPaperChange: function (e) {
    this.setData({ paperIndex: Number(e.detail.value) })
    this.refreshLayoutHint()
  },

  onLayoutChange: function (e) {
    this.setData({ layoutIndex: Number(e.detail.value) })
    this.refreshLayoutHint()
  },

  // 把「当前纸张 + 排版方式」实际会得到几栏，明确写给老师看，
  // 避免出现「选了 A3 却是 A4 排版」这种预期落差
  refreshLayoutHint: function () {
    const paper = config.paperSizes[this.data.paperIndex]
    const mode = config.layoutModes[this.data.layoutIndex].value

    let columns
    if (mode === 'single') {
      columns = 1
    } else if (mode === 'double') {
      // 栏太窄时后端不给分栏，会回退单栏 —— 这里保持一致，免得老师预期落空
      columns = paper.canDouble ? 2 : 1
    } else {
      columns = paper.columns
    }

    let hint = columns === 2 ? '当前排版：双栏' : '当前排版：单栏'
    if (mode === 'double' && !paper.canDouble) {
      hint += '（这种纸太窄，放不下双栏）'
    }
    this.setData({ layoutHint: hint })
  },
  onModeChange: function (e) { this.setData({ mode: e.currentTarget.dataset.mode }) },

  // ─── AI 生成 ───
  onAiTopicInput: function (e) { this.setData({ aiTopic: e.detail.value }) },
  onAiTermChange: function (e) { this.setData({ aiTermIndex: Number(e.detail.value) }) },
  onAiDifficultyChange: function (e) { this.setData({ aiDifficultyIndex: Number(e.detail.value) }) },

  onAiCountMinus: function (e) {
    this.changeAiTypeCount(Number(e.currentTarget.dataset.index), -1)
  },
  onAiCountPlus: function (e) {
    this.changeAiTypeCount(Number(e.currentTarget.dataset.index), 1)
  },
  onAiCountInput: function (e) {
    const idx = Number(e.currentTarget.dataset.index)
    let n = parseInt(e.detail.value, 10)
    if (isNaN(n)) n = 0
    this.setAiTypeCount(idx, n)
  },

  changeAiTypeCount: function (idx, delta) {
    const current = this.data.aiTypes[idx]
    if (!current) return
    this.setAiTypeCount(idx, current.count + delta)
  },

  setAiTypeCount: function (idx, value) {
    const types = this.data.aiTypes.slice()
    if (!types[idx]) return
    types[idx].count = Math.max(0, Math.min(30, value))
    this.setData({ aiTypes: types })
  },

  // ─── 自己出题 ───
  onCountMinus: function () {
    this.setData({ questionCount: Math.max(1, this.data.questionCount - 1) })
  },
  onCountPlus: function () {
    this.setData({ questionCount: Math.min(60, this.data.questionCount + 1) })
  },
  onCountInput: function (e) {
    let n = parseInt(e.detail.value, 10)
    if (isNaN(n)) n = 1
    this.setData({ questionCount: Math.max(1, Math.min(60, n)) })
  },

  // ─── 上传材料 ───
  onChooseImage: function () {
    const that = this
    wx.chooseMedia({
      count: 9,
      mediaType: ['image'],
      sizeType: ['compressed'], // 让微信先压一道，省流量也更快
      sourceType: ['album', 'camera'],
      success: function (res) {
        const files = (res.tempFiles || []).map(function (f) {
          return { path: f.tempFilePath, name: '题目图片_' + Date.now() + '.jpg' }
        })
        that.uploadAll(files)
      },
    })
  },

  onChooseFile: function () {
    const that = this
    wx.chooseMessageFile({
      count: 5,
      type: 'file',
      extension: ['pdf', 'docx', 'txt'],
      success: function (res) {
        const files = (res.tempFiles || []).map(function (f) {
          return { path: f.path, name: f.name }
        })
        that.uploadAll(files)
      },
      fail: function () {
        wx.showToast({ title: '没有选择文件', icon: 'none' })
      },
    })
  },

  // 逐个上传（串行，便于显示进度、也避免并发把手机网络打满）
  uploadAll: function (files) {
    if (!files.length) return
    const that = this
    this.setData({ uploading: true })

    let done = 0
    const failed = []

    const next = function () {
      if (done >= files.length) {
        that.setData({ uploading: false })
        if (failed.length) {
          wx.showModal({
            title: '部分材料没上传成功',
            content: failed.join('\n'),
            showCancel: false,
          })
        } else {
          wx.showToast({ title: '已添加 ' + files.length + ' 份', icon: 'success' })
        }
        return
      }
      const f = files[done]
      wx.showLoading({ title: '上传中 ' + (done + 1) + '/' + files.length, mask: true })

      api
        .uploadMaterial(f.path, f.name)
        .then(function (res) {
          const uploads = that.data.uploads.concat([
            {
              upload_id: res.upload_id,
              kind: res.kind,
              name: res.name,
              sizeText: formatSize(res.size),
              extra: res.pages ? res.pages + ' 页' : '',
            },
          ])
          that.setData({ uploads: uploads })
        })
        .catch(function (err) {
          failed.push(f.name + '：' + err.message)
        })
        .then(function () {
          wx.hideLoading()
          done += 1
          next()
        })
    }
    next()
  },

  onRemoveUpload: function (e) {
    const idx = Number(e.currentTarget.dataset.index)
    const uploads = this.data.uploads.slice()
    uploads.splice(idx, 1)
    this.setData({ uploads: uploads })
  },

  // ─── 生成作业 ───
  onGoHistory: function () {
    wx.navigateTo({ url: '/pages/history/history' })
  },

  onLogout: function () {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出当前账号吗？',
      success: function (res) {
        if (res.confirm) {
          api.logout()
          wx.reLaunch({ url: '/pages/login/login' })
        }
      },
    })
  },

  // 主题/知识点：逗号、顿号、空格都当分隔符
  splitTopics: function (text) {
    return (text || '')
      .split(/[,，、;；\s]+/)
      .map(function (s) { return s.trim() })
      .filter(Boolean)
  },

  buildBasePayload: function () {
    const d = this.data
    const subject = config.subjects[d.subjectIndex]
    const grade = config.grades[d.gradeIndex]
    const fallbackTitle = grade.label + subject.label + '作业'

    return {
      title: d.title.trim() || fallbackTitle,
      subject: subject.value,
      subject_cn: subject.label,
      grade: grade.value,
      grade_cn: grade.label,
      class_name: d.className.trim(),
      teacher: d.teacher.trim(),
      copies: COPIES_VALUES[d.copiesIndex],
      note: d.note.trim(),
      page_size: config.paperSizes[d.paperIndex].value,
      layout: config.layoutModes[d.layoutIndex].value,
    }
  },

  // AI 模式：先出题，再创建作业草稿
  submitAi: function (base) {
    const that = this
    const d = this.data

    const requirements = d.aiTypes
      .filter(function (t) { return t.count > 0 })
      .map(function (t) { return { type: t.value, count: t.count, score: 5 } })

    if (!requirements.length) {
      wx.showToast({ title: '请至少选一种题型', icon: 'none' })
      return
    }

    const topics = this.splitTopics(d.aiTopic)
    wx.showLoading({ title: 'AI 正在出题…', mask: true })

    api
      .generateQuestionsByAI({
        topic: topics.join('、'),
        topics: topics,
        grade: base.grade_cn,               // 后端要中文年级
        term: config.terms[d.aiTermIndex],
        difficulty: config.difficulties[d.aiDifficultyIndex],
        subject: base.subject_cn,           // 后端要中文学科
        requirements: requirements,
      })
      .then(function (questions) {
        if (!questions || !questions.length) {
          throw new Error('AI 没有生成出题目，换个知识点或稍后再试')
        }
        wx.showLoading({ title: '正在生成作业纸…', mask: true })
        return that.createJob(base, {
          question_items: questions,
          // 0 = 自动，交给后端按题型决定答题行数
          answer_lines_override: d.answerLineIndex > 0 ? d.answerLineIndex : null,
        })
      })
      .catch(function (err) {
        wx.hideLoading()
        wx.showModal({ title: '生成失败', content: err.message, showCancel: false })
        that.setData({ generating: false })
      })
  },

  // 自己出题 / 上传材料：直接创建
  submitPlain: function (base, extra) {
    const that = this
    wx.showLoading({ title: '正在生成作业纸…', mask: true })
    return this.createJob(base, extra).catch(function (err) {
      wx.hideLoading()
      wx.showModal({ title: '生成失败', content: err.message, showCancel: false })
      that.setData({ generating: false })
    })
  },

  createJob: function (base, extra) {
    const payload = Object.assign({}, base, extra)
    delete payload.subject_cn
    delete payload.grade_cn

    wx.setStorageSync(LAST_PAYLOAD_KEY, payload)

    return api.createPrintJob(payload).then(function (job) {
      wx.hideLoading()
      wx.navigateTo({
        url:
          '/pages/result/result?jobId=' + job.job_id +
          '&title=' + encodeURIComponent(base.title),
      })
    })
  },

  onSubmit: function () {
    if (this.data.generating) return
    const d = this.data
    const base = this.buildBasePayload()

    if (d.mode === 'upload' && !d.uploads.length) {
      wx.showToast({ title: '请先添加题目图片或文档', icon: 'none' })
      return
    }

    this.setData({ generating: true })

    if (d.mode === 'ai') {
      this.submitAi(base)
      return
    }

    if (d.mode === 'upload') {
      this.submitPlain(base, {
        upload_ids: d.uploads.map(function (u) { return u.upload_id }),
        upload_answer_lines: d.answerLineIndex,
      })
      return
    }

    // 自己出题：只给题量，生成空白答题纸
    this.submitPlain(base, {
      question_count: d.questionCount,
      answer_lines: d.answerLineIndex > 0 ? d.answerLineIndex : 2,
    })
  },
})
