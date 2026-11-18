const api = require('../../utils/api')

Page({
  data: {
    mine: {
      avatar: '🐼',
      name: '老师',
      email: '',
      subject: '',
      role: '',
      jobTitle: '',
      classCount: 0,
      studentCount: 0,
      weekGrades: 0,
    },
  },

  onShow: function () {
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
      return
    }
    this.loadMine()
  },

  loadMine: function () {
    const that = this
    const user = api.getUser() || {}
    this.setData({
      'mine.name': user.display_name || user.name || user.username || '老师',
      'mine.email': user.email || '',
      'mine.subject': user.teaching_subject || '',
      'mine.role': (user.roles && user.roles[0]) || '',
      'mine.jobTitle': user.job_title || '',
    })

    // 刷新最新资料（失败不打扰）
    if (api.getMe) {
      api
        .getMe()
        .then(function (me) {
          if (!me) return
          that.setData({
            'mine.name': me.display_name || me.name || that.data.mine.name,
            'mine.email': me.email || that.data.mine.email,
            'mine.subject': me.teaching_subject || that.data.mine.subject,
            'mine.role': (me.roles && me.roles[0]) || that.data.mine.role,
            'mine.jobTitle': me.job_title || that.data.mine.jobTitle,
          })
        })
        .catch(function () {})
    }

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
        that.setData({ 'mine.weekGrades': week })
      })
      .catch(function () {})
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

  onGoPrintHistory: function () {
    wx.navigateTo({ url: '/pages/history/history' })
  },

  onGoDashboard: function () {
    wx.navigateTo({ url: '/pages/dashboard/dashboard' })
  },

  onGoAdminOverview: function () {
    wx.navigateTo({ url: '/pages/admin-overview/admin-overview' })
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
})
