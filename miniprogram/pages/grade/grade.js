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
    this.refresh().then(function (status) {
      that.setData({ loading: false })
      const ended = status === 'done' || status === 'failed' || status === 'cancelled' || status === 'error'
      if (!ended) that.startPolling()
    })
  },

  // ─── 拉取 / 轮询 ───
  refresh: function () {
    const that = this
    return api
      .getGradeHome(this.data.jobId)
      .then(function (res) {
        const item = res.item || {}
        const status = item.status || ''
        that.setData({
          status: status,
          statusText: STATUS_TEXT[status] || status,
          progress: item.progress || 0,
          message: item.message || '',
          result: item.result || '',
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

  // ─── 其他 ───
  onReset: function () {
    this.stopPolling()
    this.setData({
      mode: 'upload', jobId: '', name: '', imagePath: '', standardPath: '',
      status: '', statusText: '', progress: 0, message: '', result: '',
      imageAnnotated: '', imageOriginal: '', imageMarksOnly: '', viewing: 'annotated',
      zoom: 1, zoomText: '100%',
      grading: false, loading: false, error: '',
    })
  },

  onGoHistory: function () {
    wx.navigateTo({ url: '/pages/grade-history/grade-history' })
  },
})
