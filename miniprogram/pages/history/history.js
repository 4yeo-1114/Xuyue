const api = require('../../utils/api')

const STATUS_TEXT = {
  draft: '未打印',
  pending: '排队中',
  printing: '打印中',
  done: '已打印',
  failed: '打印失败',
}

const SOURCE_UNIT = {
  upload: '份材料',
  ai: '道题',
  text: '道题',
}

Page({
  data: {
    jobs: [],
    loading: true,
    error: '',
  },

  onLoad: function () {
    this.load()
  },

  onPullDownRefresh: function () {
    const that = this
    this.load().then(function () {
      wx.stopPullDownRefresh()
    })
  },

  load: function () {
    const that = this
    this.setData({ loading: true, error: '' })
    return api
      .listPrintJobs(50)
      .then(function (res) {
        const jobs = (res.jobs || []).map(function (j) {
          return Object.assign({}, j, {
            statusText: STATUS_TEXT[j.status] || j.status,
            timeText: that.formatTime(j.created_at),
            metaText: [j.grade_label, j.subject_label, j.class_name]
              .filter(Boolean)
              .join(' · '),
            pageLabel: j.page_size_label || '',
            countText: j.question_count + ' ' + (SOURCE_UNIT[j.source] || '道题'),
          })
        })
        that.setData({ jobs: jobs, loading: false })
      })
      .catch(function (err) {
        that.setData({ error: err.message, loading: false })
      })
  },

  // 后端返回的是 ISO 时间串，这里只取「月-日 时:分」
  formatTime: function (iso) {
    if (!iso) return ''
    const d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    const pad = function (n) { return n < 10 ? '0' + n : '' + n }
    return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
  },

  onTapJob: function (e) {
    const job = this.data.jobs[e.currentTarget.dataset.index]
    wx.navigateTo({
      url:
        '/pages/result/result?jobId=' + job.job_id +
        '&title=' + encodeURIComponent(job.title || '作业纸'),
    })
  },
})
