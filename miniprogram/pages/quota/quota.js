const api = require('../../utils/api')

// 额度展示页（充值/支付 20261111 随「余额/充值/支付整体移除」删掉，只留用量）
Page({
  data: {
    usage: { total_pages: 0, used_pages: 0, available: 0, used_pct: 0, locked: false, today_pages: 0 },
  },

  onLoad: function () {
    this.loadQuota()
  },

  onPullDownRefresh: function () {
    const that = this
    this.loadQuota().then(function () {
      wx.stopPullDownRefresh()
    })
  },

  loadQuota: function () {
    const that = this
    return api
      .getQuota()
      .then(function (u) {
        that.setData({ usage: u || that.data.usage })
      })
      .catch(function (err) {
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },
})
