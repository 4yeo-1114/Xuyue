const api = require('../../utils/api')

Page({
  data: {},

  onShow: function () {
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
  },

  onGoGradeHistory: function () {
    wx.navigateTo({ url: '/pages/grade-history/grade-history' })
  },

  onGoScores: function () {
    wx.navigateTo({ url: '/pages/scores/scores' })
  },

  onGoErrors: function () {
    wx.navigateTo({ url: '/pages/errors/errors' })
  },

  onGoLedger: function () {
    wx.navigateTo({ url: '/pages/ledger/ledger' })
  },

  onGoStudents: function () {
    wx.navigateTo({ url: '/pages/students/students' })
  },

  onGoKnowledge: function () {
    wx.navigateTo({ url: '/pages/knowledge/knowledge' })
  },

  onGoTasks: function () {
    wx.navigateTo({ url: '/pages/tasks/tasks' })
  },

  onGoPapers: function () {
    wx.navigateTo({ url: '/pages/papers/papers' })
  },

  onGoClasses: function () {
    wx.navigateTo({ url: '/pages/classes/classes' })
  },

  onGoPrintHistory: function () {
    wx.navigateTo({ url: '/pages/history/history' })
  },

  onGoQuota: function () {
    wx.navigateTo({ url: '/pages/quota/quota' })
  },

  onGoDashboard: function () {
    wx.navigateTo({ url: '/pages/dashboard/dashboard' })
  },

  onGoAdminOverview: function () {
    wx.navigateTo({ url: '/pages/admin-overview/admin-overview' })
  },
})
