const api = require('../../utils/api')
const config = require('../../utils/config')

const STATUS_TEXT = {
  queued: '排队中',
  running: '批改中',
  rendering: '生成留痕',
  done: '已完成',
  failed: '批改失败',
  cancelled: '已取消',
}

// 判定徽章样式与同题多作答区的「最差判定」优先级
const BADGE_CLASS = {
  '对': 'ok',
  '错': 'bad',
  '半对': 'half',
  '未作答': 'blank',
  '未批': 'muted',
  '待确认': 'warn',
}
const RESULT_RANK = { '错': 5, '半对': 4, '待确认': 3, '未作答': 2, '未批': 1, '对': 0, '': 0 }

// 题号 key：与后端 question_key_of 一致（index → label 数字前缀 → slot_id）
function questionKeyOf(blk) {
  const idx = blk.index
  if (idx !== undefined && idx !== null && String(idx).trim() && String(idx).trim() !== 'None') {
    return String(idx).trim()
  }
  const label = String(blk.label || '').trim()
  if (label) {
    const m = label.match(/^(\d+)/)
    return m ? m[1] : label
  }
  return String(blk.slot_id || '').trim()
}

// blocks + 判错批注 → 一题一张卡（同题多作答区合并，取最差判定）
function buildQuestionCards(blocks, wrongs) {
  const byKey = {}
  const order = []
  ;(blocks || []).forEach(function (b) {
    if (!b || typeof b !== 'object') return
    const key = questionKeyOf(b)
    if (!key) return
    if (!byKey[key]) {
      byKey[key] = { key: key, subs: [], result: '', badge: '', score: 0, hasScore: false, comments: [], answers: [], corrects: [] }
      order.push(key)
    }
    const card = byKey[key]
    const res = String(b.result || '').trim()
    card.subs.push({ sub_index: b.sub_index || 1, result: res, badge: BADGE_CLASS[res] || 'muted' })
    // 首个判定直接落位（「对」rank=0 盖不过初始空串，不能只比大小）
    if (res && (card.result === '' || (RESULT_RANK[res] || 0) > (RESULT_RANK[card.result] || 0))) card.result = res
    if (typeof b.score === 'number' && isFinite(b.score)) {
      card.score += b.score
      card.hasScore = true
    }
    const c = String(b.comment || '').trim()
    if (c && card.comments.indexOf(c) < 0) card.comments.push(c)
    const a = String(b.transcription || b.answer_text || '').trim()
    if (a && card.answers.indexOf(a) < 0) card.answers.push(a)
    // 参考答案：答案卷/标准答案路径才带（correct_answer / interpretation_text）
    const ca = String(b.correct_answer || b.interpretation_text || '').trim()
    if (ca && card.corrects.indexOf(ca) < 0) card.corrects.push(ca)
  })

  return order.map(function (key) {
    const card = byKey[key]
    const anno = wrongs && wrongs[key] ? String((wrongs[key] || {}).text || '').trim() : ''
    const commentText = card.comments.join('；')
    const answerText = card.answers.join('\n')
    return {
      key: key,
      title: '第' + key + '题' + (card.subs.length > 1 ? ' · ' + card.subs.length + ' 个作答区' : ''),
      result: card.result || '—',
      badge: BADGE_CLASS[card.result] || 'muted',
      scoreText: card.hasScore ? '得 ' + (Math.round(card.score * 10) / 10) + ' 分' : '',
      preview: anno || commentText || answerText,
      answerText: answerText,
      correctText: card.corrects.join('\n'),
      commentText: commentText,
      annotation: anno,
      subs: card.subs,
      expanded: false,
    }
  })
}

function summarizeQuestions(questions) {
  const s = { ok: 0, bad: 0, half: 0, blank: 0, other: 0 }
  ;(questions || []).forEach(function (q) {
    if (q.result === '对') s.ok++
    else if (q.result === '错') s.bad++
    else if (q.result === '半对') s.half++
    else if (q.result === '未作答') s.blank++
    else s.other++
  })
  return s
}

Page({
  data: {
    mode: 'upload',   // upload = 新批改；detail = 历史回看
    jobId: '',
    name: '',
    imagePath: '',    // 学生卷选图预览
    standardPath: '', // 标准答案卷（可选，有则走千问对照批改）

    status: '',
    statusText: '',
    progress: 0,
    message: '',
    result: '',
    questions: [],
    summary: { ok: 0, bad: 0, half: 0, blank: 0, other: 0 },
    wrongCount: 0,
    imageAnnotated: '',
    imageOriginal: '',
    imageMarksOnly: '',
    viewing: 'annotated',
    zoom: 1,
    zoomText: '100%',

    grading: false,
    loading: false,
    error: '',
  },

  onLoad: function (options) {
    if (options && options.jobId) {
      this.setData({ mode: 'detail', jobId: options.jobId, loading: true })
      this.loadDetail()
    }
  },

  onUnload: function () {
    this.stopPolling()
    if (this._annoTimer) {
      clearTimeout(this._annoTimer)
      this._annoTimer = null
    }
  },

  // ─── 上传模式 ───
  onChooseImage: function () {
    const that = this
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: function (res) {
        const f = res.tempFiles && res.tempFiles[0]
        if (f) that.setData({ imagePath: f.tempFilePath })
      },
    })
  },

  onChooseStandard: function () {
    const that = this
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: function (res) {
        const f = res.tempFiles && res.tempFiles[0]
        if (f) that.setData({ standardPath: f.tempFilePath })
      },
    })
  },

  onStartGrade: function () {
    if (this.data.grading) return
    if (!this.data.imagePath) {
      wx.showToast({ title: '请先选择试卷图片', icon: 'none' })
      return
    }
    const that = this
    this.setData({ grading: true, error: '' })
    wx.showLoading({ title: '上传中…', mask: true })

    const run = function (standardId) {
      api
        .gradeHomeQuick(that.data.imagePath, standardId)
        .then(function (res) {
          wx.hideLoading()
          const item = res.item || {}
          that.setData({
            mode: 'result',
            jobId: res.job_id,
            status: item.status || 'queued',
            statusText: STATUS_TEXT[item.status] || '排队中',
            progress: item.progress || 5,
            message: item.message || '已上传，等待开始…',
          })
          that.startPolling()
        })
        .catch(function (err) {
          wx.hideLoading()
          that.setData({ grading: false })
          wx.showModal({ title: '上传失败', content: err.message, showCancel: false })
        })
    }

    // 选了标准答案卷就先把答案卷传上去，拿到 id 再带着它上传学生卷（走千问对照批改）
    if (this.data.standardPath) {
      api
        .uploadHomeStandard(this.data.standardPath)
        .then(function (standardId) {
          run(standardId)
        })
        .catch(function (err) {
          wx.hideLoading()
          that.setData({ grading: false })
          wx.showModal({ title: '答案卷上传失败', content: err.message, showCancel: false })
        })
    } else {
      run('')
    }
  },

  // ─── 详情回看 ───
  loadDetail: function () {
    const that = this
    this._annoRefreshed = false
    this.refresh().then(function (status) {
      that.setData({ loading: false })
      const ended = status === 'done' || status === 'failed' || status === 'cancelled' || status === 'error'
      if (!ended) that.startPolling()
      else if (status === 'done') that.scheduleAnnotationRefresh()
    })
  },

  // 判错批注是批完后异步生成的：完成后延时补拉一次，让「错因解析」不缺席
  scheduleAnnotationRefresh: function () {
    const that = this
    if (this._annoRefreshed || this._annoTimer) return
    this._annoTimer = setTimeout(function () {
      that._annoTimer = null
      that._annoRefreshed = true
      that.refresh()
    }, 10000)
  },

  // ─── 拉取 / 轮询 ───
  refresh: function () {
    const that = this
    return api
      .getGradeHome(this.data.jobId)
      .then(function (res) {
        const item = res.item || {}
        const status = item.status || ''
        // 逐题卡片：blocks 分组 + 判错批注当解析；保留已展开的题免得刷新收起
        const prevExpanded = {}
        ;(that.data.questions || []).forEach(function (q) {
          if (q.expanded) prevExpanded[q.key] = true
        })
        const questions = buildQuestionCards(item.blocks, item.wrong_annotations || {})
        questions.forEach(function (q) {
          if (prevExpanded[q.key]) q.expanded = true
        })
        that.setData({
          status: status,
          statusText: STATUS_TEXT[status] || status,
          progress: item.progress || 0,
          message: item.message || '',
          result: item.result || '',
          questions: questions,
          summary: summarizeQuestions(questions),
          wrongCount: questions.filter(function (q) {
            return q.result === '错' || q.result === '半对'
          }).length,
          imageAnnotated: api.resolveFileUrl(item.image_annotated),
          imageOriginal: api.resolveFileUrl(item.image_original),
          imageMarksOnly: api.resolveFileUrl(item.image_marks_only),
          name: item.name || that.data.name,
        })
        // 留痕图缺失时回退到原图
        if (that.data.viewing === 'annotated' && !that.data.imageAnnotated && that.data.imageOriginal) {
          that.setData({ viewing: 'original' })
        }
        return status
      })
      .catch(function (err) {
        that.setData({ error: err.message })
        return 'error'
      })
  },

  startPolling: function () {
    const that = this
    this.setData({ grading: true })
    this.stopPolling()
    const startedAt = Date.now()

    const tick = function () {
      that.pollTimer = setTimeout(function () {
        that.refresh().then(function (status) {
          if (status === 'done' || status === 'failed' || status === 'cancelled' || status === 'error') {
            that.setData({ grading: false })
            if (status === 'done') that.scheduleAnnotationRefresh()
            return
          }
          if (Date.now() - startedAt > config.pollTimeout) {
            that.setData({ grading: false })
            that.setData({ message: '批改时间较长，请稍后在批改历史里查看' })
            return
          }
          tick()
        })
      }, config.pollInterval)
    }
    tick()
  },

  stopPolling: function () {
    if (this.pollTimer) {
      clearTimeout(this.pollTimer)
      this.pollTimer = null
    }
  },

  // ─── 图片切换 / 缩放 ───
  onSwitchImage: function (e) {
    const v = e.currentTarget.dataset.view
    if (v === 'annotated' && !this.data.imageAnnotated) return
    if (v === 'original' && !this.data.imageOriginal) return
    this.setData({ viewing: v, zoom: 1, zoomText: '100%' })
  },

  onZoomIn: function () {
    this.setZoom(Math.min(5, this.data.zoom + 0.5))
  },

  onZoomOut: function () {
    this.setZoom(Math.max(1, this.data.zoom - 0.5))
  },

  onZoomReset: function () {
    this.setZoom(1)
  },

  setZoom: function (z) {
    z = Math.round(z * 100) / 100
    this.setData({ zoom: z, zoomText: Math.round(z * 100) + '%' })
  },

  // 手指双指缩放时同步比例，让按钮上的百分比跟着变
  onScale: function (e) {
    const scale = e.detail && e.detail.scale
    if (scale) {
      const s = Math.round(scale * 100) / 100
      this.setData({ zoom: s, zoomText: Math.round(s * 100) + '%' })
    }
  },

  // ─── 批改明细卡片 ───
  onToggleQuestion: function (e) {
    const index = Number(e.currentTarget.dataset.index)
    const key = 'questions[' + index + '].expanded'
    const q = this.data.questions[index]
    if (!q) return
    this.setData({ [key]: !q.expanded })
  },

  // 错题举一反三 → 变式题页（拆页放，别堆在结果页）
  onGoVariants: function () {
    wx.navigateTo({
      url: '/pages/variants/variants?jobId=' + encodeURIComponent(this.data.jobId),
    })
  },

  // ─── 其他 ───
  onReset: function () {
    this.stopPolling()
    this.setData({
      mode: 'upload', jobId: '', name: '', imagePath: '', standardPath: '',
      status: '', statusText: '', progress: 0, message: '', result: '',
      questions: [], summary: { ok: 0, bad: 0, half: 0, blank: 0, other: 0 }, wrongCount: 0,
      imageAnnotated: '', imageOriginal: '', imageMarksOnly: '', viewing: 'annotated',
      zoom: 1, zoomText: '100%',
      grading: false, loading: false, error: '',
    })
  },

  onGoHistory: function () {
    wx.navigateTo({ url: '/pages/grade-history/grade-history' })
  },
})
