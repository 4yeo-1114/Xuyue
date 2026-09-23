// 小程序入口

const api = require('./utils/api')

App({
  globalData: {
    // 结果页回退到首页时，用它告诉首页刷新打印记录
    needRefreshHistory: false,
  },

  onLaunch: function () {
    // 已登录就直接进首页，否则去登录页
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
  },
})
