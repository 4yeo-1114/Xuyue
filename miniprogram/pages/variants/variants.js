const api = require('../../utils/api')

// 错题举一反三：本次批改的错题 → AI 变式题（答案/解析点开看）→ 一键出成试卷存进试卷库。
// 生成在后端 /grading/home/{jobId}/variants（重 LLM，约 1 分钟），结果幂等缓存在作业记录里。
Page({
  data: {
    jobId: '',
    subjectLabels: ['综合', '语文', '数学', '英语', '物理', '化学', '生物', '历史', '地理', '政治', '科学'],
    subjectIndex: 0,
    generating: false,
    items: [],
    wrongCount: 0,
    failedCount: 0,
    generatedAt: '',
    error: '',
    saving: false,
    saved: false,
  },

  onLoad: function (options) {
    const jobId = (options && options.jobId) || ''
    if (!jobId) {
      this.setData({ error: '缺少批改记录' })
      return
    }
    this.setData({ jobId: jobId })
    this.generate(false)
  },

  onPullDownRefresh: function () {
    const that = this
    this.generate(false).then(function () {
      wx.stopPullDownRefresh()
    })
  },

  onSubjectChange: function (e) {
    this.setData({ subjectIndex: Number(e.detail.value) || 0 })
  },

  // force=false 走后端缓存（已生成过直接拿），true 强制重出
  generate: function (force) {
    if (this.data.generating) return Promise.resolve()
    const that = this
    this.setData({ generating: true, error: '', saved: false })
    return api
      .generateHomeVariants(this.data.jobId, {
        subject: this.data.subjectLabels[this.data.subjectIndex] === '综合'
          ? ''
          : this.data.subjectLabels[this.data.subjectIndex],
        count_per_question: 2,
        force: !!force,
      })
      .then(function (res) {
        const items = (res.items || []).map(function (it, i) {
          return {
            idx: i,
            no: it.no || (i + 1),
            from_title: it.from_title || '',
            orig_result: it.orig_result || '',
            question: it.question || '',
            answer: it.answer || '',
            analysis: it.analysis || '',
            kp_name: it.kp_name || '',
            _type: it.type || 'short_answer',
            _content: it.content || it.question || '',
            _options: it.options || [],
            expanded: false,
          }
        })
        that.setData({
          generating: false,
          items: items,
          wrongCount: res.wrong_count || 0,
          failedCount: (res.failed_keys || []).length,
          generatedAt: (res.generated_at || '').replace('T', ' ').slice(0, 16),
        })
      })
      .catch(function (err) {
        that.setData({ generating: false, error: err.message })
      })
  },

  onRegenerate: function () {
    this.generate(true)
  },

  onToggle: function (e) {
    const index = Number(e.currentTarget.dataset.index)
    const key = 'items[' + index + '].expanded'
    const it = this.data.items[index]
    if (!it) return
    this.setData({ [key]: !it.expanded })
  },

  // 出成试卷：与网页版「智能组卷」同一份试卷库，出完可去「试卷库」一键布置
  onSavePaper: function () {
    if (this.data.saving || !this.data.items.length) return
    const that = this
    const subject = this.data.subjectLabels[this.data.subjectIndex]
    const questions = this.data.items.map(function (it, i) {
      return {
        id: 'variant_' + (i + 1),
        type: it._type,
        stem: '',
        content: it._content,
        score: 5,
        options: it._options,
        subQuestions: [],
        answer: it.answer,
        analysis: it.analysis,
      }
    })
    const d = new Date()
    const pad = function (n) { return (n < 10 ? '0' : '') + n }
    const title = '举一反三练习-' + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate())
    this.setData({ saving: true })
    api
      .saveExamPaper(title, subject, questions)
      .then(function () {
        that.setData({ saving: false, saved: true })
        wx.showToast({ title: '已存入试卷库', icon: 'success' })
      })
      .catch(function (err) {
        that.setData({ saving: false })
        wx.showModal({ title: '出卷失败', content: err.message, showCancel: false })
      })
  },

  onGoPapers: function () {
    wx.navigateTo({ url: '/pages/papers/papers' })
  },
})
