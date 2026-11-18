const api = require('../../utils/api')

const STATUS_TEXT = {
  queued: '排队中',
  running: '批改中',
  rendering: '生成留痕',
  done: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

Page({
  data: {
    loading: true,
    stats: {
      classCount: 0,
      studentCount: 0,
      weekGrades: 0,
      quotaLeft: 0,
      quotaUsed: 0,
      quotaTotal: 0,
      quotaUsedPct: 0,
      todayPages: 0,
    },
    classes: [],
    recent: [],
  },

  onLoad: function () {
    this.load()
  },

  onShow: function () {
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
  },

  onPullDownRefresh: function () {
    const that = this
    this.load().then(function () {
      wx.stopPullDownRefresh()
    })
  },

  // 三路并发：班级 / 最近批改 / 额度，谁快谁先上屏
  load: function () {
    const that = this
    this.setData({ loading: true })

    const pClasses = api
      .listClasses()
      .then(function (rows) {
        const classes = rows || []
        let students = 0
        classes.forEach(function (c) {
          students += c.student_count || 0
        })
        that.setData({
          'stats.classCount': classes.length,
          'stats.studentCount': students,
          classes: classes.slice(0, 6),
        })
      })
      .catch(function () {})

    const pRecent = api
      .listGradeHomeRecent()
      .then(function (res) {
        const items = (res && res.items) || []
        const weekAgo = Date.now() - 7 * 24 * 3600 * 1000
        let week = 0
        items.forEach(function (it) {
          const t = Date.parse(it.created_at || '')
          if (!isNaN(t) && t >= weekAgo) week += 1
        })
        that.setData({
          'stats.weekGrades': week,
          recent: items.slice(0, 8).map(function (it) {
            return Object.assign({}, it, {
              statusText: STATUS_TEXT[it.status] || it.status,
              timeText: that.formatTime(it.created_at),
            })
          }),
        })
      })
      .catch(function () {})

    const pQuota = api
      .getQuota()
      .then(function (q) {
        that.setData({
          'stats.quotaLeft': (q && q.available) || 0,
          'stats.quotaUsed': (q && q.used_pages) || 0,
          'stats.quotaTotal': (q && q.total_pages) || 0,
          'stats.quotaUsedPct': (q && q.used_pct) || 0,
          'stats.todayPages': (q && q.today_pages) || 0,
        })
      })
      .catch(function () {})

    return Promise.all([pClasses, pRecent, pQuota]).then(function () {
      that.setData({ loading: false })
    })
  },

  formatTime: function (iso) {
    if (!iso) return ''
    const d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    const pad = function (n) { return n < 10 ? '0' + n : '' + n }
    return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
  },

  onGoClasses: function () {
    wx.navigateTo({ url: '/pages/classes/classes' })
  },

  onGoStudents: function () {
    wx.navigateTo({ url: '/pages/students/students' })
  },

  onGoGradeHistory: function () {
    wx.navigateTo({ url: '/pages/grade-history/grade-history' })
  },

  onGoQuota: function () {
    wx.navigateTo({ url: '/pages/quota/quota' })
  },
})
