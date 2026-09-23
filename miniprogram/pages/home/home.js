const api = require('../../utils/api')

Page({
  data: {},

  onShow: function () {
    // 未登录先回登录页
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
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

  onGoPrintHistory: function () {
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
})
