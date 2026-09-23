const api = require('../../utils/api')
const config = require('../../utils/config')

const LAST_PAYLOAD_KEY = 'xuyue_last_payload'

const STATUS_TEXT = {
  draft: '未打印',
  pending: '排队中',
  printing: '打印中',
  done: '已打印',
  failed: '打印失败',
}

Page({
  data: {
    jobId: '',
    title: '',
    status: 'draft',
    statusText: '未打印',
    printer: '',
    error: '',
    copies: 1,
    questionCount: 0,
    sourceText: '',
    pageSizeLabel: '',

    loading: true,
    previewing: false,
    printing: false,
    reprinting: false,
    timedOut: false,
  },

  onLoad: function (options) {
    this.setData({
      jobId: options.jobId || '',
      title: decodeURIComponent(options.title || '作业'),
    })
    this.refresh()
  },

  onUnload: function () {
    this.stopPolling()
  },

  // ─── 状态 ───
  refresh: function () {
    const that = this
    return api
      .getPrintJob(this.data.jobId)
      .then(function (job) {
        const status = job.status || 'draft'
        that.setData({
          loading: false,
          status: status,
          statusText: STATUS_TEXT[status] || status,
          printer: job.printer || '',
          error: job.error || '',
          copies: job.copies || 1,
          questionCount: job.question_count || 0,
          pageSizeLabel: job.page_size_label || '',
          sourceText:
            job.source === 'upload' ? '份材料' : (job.source === 'ai' ? '道题' : '道题'),
        })
        return status
      })
      .catch(function (err) {
        that.setData({ loading: false, error: err.message })
        return 'error'
      })
  },

  // 送出打印后开始盯状态
  startPolling: function () {
    const that = this
    const startedAt = Date.now()

    const tick = function () {
      that.pollTimer = setTimeout(function () {
        that.refresh().then(function (status) {
          if (status === 'done' || status === 'failed' || status === 'error') {
            that.stopPolling()
            if (status === 'done') {
              wx.showToast({ title: '已送到打印机', icon: 'success' })
            }
            return
          }
          if (Date.now() - startedAt > config.pollTimeout) {
            that.stopPolling()
            that.setData({ timedOut: true })
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

  // ─── 预览 ───
  onPreview: function () {
    const that = this
    this.setData({ previewing: true })
    wx.showLoading({ title: '正在打开…', mask: true })

    api
      .downloadWorksheet(this.data.jobId)
      .then(function (path) {
        wx.hideLoading()
        return api.previewPdf(path)
      })
      .catch(function (err) {
        wx.hideLoading()
        wx.showModal({ title: '打不开预览', content: err.message, showCancel: false })
      })
      .then(function () {
        that.setData({ previewing: false })
      })
  },

  // ─── 打印 ───
  onPrint: function () {
    const that = this
    this.setData({ printing: true, timedOut: false })

    api
      .printJob(this.data.jobId)
      .then(function (job) {
        that.setData({
          status: job.status,
          statusText: STATUS_TEXT[job.status] || job.status,
        })
        wx.showToast({ title: '已发送到打印机', icon: 'success' })
        that.startPolling()
      })
      .catch(function (err) {
        wx.showModal({ title: '打印失败', content: err.message, showCancel: false })
        that.refresh()
      })
      .then(function () {
        that.setData({ printing: false })
      })
  },

  // ─── 返回修改 ───
  // 作业还在草稿状态，直接返回上一页；表单里的内容都还在，改完再生成即可
  onBack: function () {
    wx.navigateBack({
      fail: function () {
        wx.reLaunch({ url: '/pages/index/index' })
      },
    })
  },

  // ─── 再打一份（用同样的内容重新生成一份作业）───
  onReprint: function () {
    const payload = wx.getStorageSync(LAST_PAYLOAD_KEY)
    if (!payload) {
      wx.showToast({ title: '找不到上次的作业内容', icon: 'none' })
      return
    }

    const that = this
    this.setData({ reprinting: true })
    wx.showLoading({ title: '正在重新生成…', mask: true })

    api
      .createPrintJob(payload)
      .then(function (job) {
        wx.hideLoading()
        that.stopPolling()
        that.setData({
          jobId: job.job_id,
          status: 'draft',
          statusText: STATUS_TEXT.draft,
          printer: '',
          error: '',
          timedOut: false,
        })
        wx.showToast({ title: '已重新生成，可以打印了', icon: 'none' })
      })
      .catch(function (err) {
        wx.hideLoading()
        wx.showModal({ title: '生成失败', content: err.message, showCancel: false })
      })
      .then(function () {
        that.setData({ reprinting: false })
      })
  },

  // ─── 删除这份作业 ───
  onDelete: function () {
    const that = this
    wx.showModal({
      title: '删除作业',
      content: '这份作业还没打印，删掉就没有了。确定吗？',
      success: function (res) {
        if (!res.confirm) return
        api
          .cancelPrintJob(that.data.jobId)
          .then(function () {
            wx.showToast({ title: '已删除', icon: 'success' })
            setTimeout(function () {
              that.onBack()
            }, 600)
          })
          .catch(function (err) {
            wx.showModal({ title: '删除失败', content: err.message, showCancel: false })
          })
      },
    })
  },

  onGoHome: function () {
    wx.reLaunch({ url: '/pages/index/index' })
  },
})
