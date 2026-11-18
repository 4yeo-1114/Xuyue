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
    mine: {
      avatar: '🐼',
      name: '老师',
      subject: '',
      role: '',
      classCount: 0,
      studentCount: 0,
      weekGrades: 0,
    },
    recent: [],
  },

  onShow: function () {
    // 未登录先回登录页
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
      return
    }
    this.loadMine()
  },

  // 「我的」名片：用户信息 + 我的数据（班级/学生/本周批改）
  loadMine: function () {
    const that = this
    const user = api.getUser() || {}
    this.setData({
      'mine.name': user.display_name || user.name || user.username || '老师',
      'mine.subject': user.teaching_subject || '',
      'mine.role': (user.roles && user.roles[0]) || '',
    })

    api
      .listClasses()
      .then(function (rows) {
        const classes = rows || []
        let students = 0
        classes.forEach(function (c) {
          students += c.student_count || 0
        })
        that.setData({
          'mine.classCount': classes.length,
          'mine.studentCount': students,
        })
      })
      .catch(function () {})

    api
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
          'mine.weekGrades': week,
          // 最近批改流：只展示最近 5 条
          recent: items.slice(0, 5).map(function (it) {
            return Object.assign({}, it, {
              statusText: STATUS_TEXT[it.status] || it.status,
              timeText: that.formatTime(it.created_at),
            })
          }),
        })
      })
      .catch(function () {})
  },

  formatTime: function (iso) {
    if (!iso) return ''
    const d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    const pad = function (n) { return n < 10 ? '0' + n : '' + n }
    return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
  },

  onGoMine: function () {
    // 「我的」是 tab 页，只能 switchTab
    wx.switchTab({ url: '/pages/mine/mine' })
  },

  onGoAssign: function () {
    wx.navigateTo({ url: '/pages/index/index' })
  },

  onGoGrade: function () {
    wx.navigateTo({ url: '/pages/grade/grade' })
  },

  onGoGradeHistory: function () {
    wx.navigateTo({ url: '/pages/grade-history/grade-history' })
  },

  onGoStudents: function () {
    wx.navigateTo({ url: '/pages/students/students' })
  },

  onGoClasses: function () {
    wx.navigateTo({ url: '/pages/classes/classes' })
  },

})
