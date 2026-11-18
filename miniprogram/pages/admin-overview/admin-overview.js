const api = require('../../utils/api')

// 账号总览（充值/钱包 20261111 随「余额/充值/支付整体移除」删掉，只留用量/额度）
Page({
  data: {
    loading: true,
    denied: false,
    error: '',
    totalAccounts: 0,
    windowDays: 30,
    scopeNote: '',
    summary: {
      totalGradeLifetime: 0,
      totalUploadLifetime: 0,
    },
    groups: [],
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

  load: function () {
    const that = this
    this.setData({ loading: true, denied: false, error: '' })
    return api
      .getAdminOverview(30)
      .then(function (res) {
        const items = (res && res.items) || []
        // 按邮箱域名（文件夹）分组
        const order = []
        const byGroup = {}
        items.forEach(function (it) {
          const g = it.group || '未分组'
          if (!byGroup[g]) {
            byGroup[g] = []
            order.push(g)
          }
          byGroup[g].push({
            key: it.user_id,
            name: it.display_name || it.email || it.user_id,
            email: it.email || '',
            role: (it.roles && it.roles[0]) || '',
            gradeLife: (it.usage && it.usage.grade_lifetime) || 0,
            recent: (it.usage && it.usage.grade_recent) || 0,
            usedPct: (it.quota && it.quota.used_pct) || 0,
          })
        })
        const groups = order.map(function (g) {
          return { name: g, count: byGroup[g].length, rows: byGroup[g] }
        })
        const summary = (res && res.summary) || {}
        that.setData({
          loading: false,
          totalAccounts: (res && res.total_accounts) || items.length,
          windowDays: (res && res.window_days) || 30,
          scopeNote: (res && res.scope_note) || '',
          summary: {
            totalGradeLifetime: summary.total_grade_lifetime || 0,
            totalUploadLifetime: summary.total_upload_lifetime || 0,
          },
          groups: groups,
        })
      })
      .catch(function (err) {
        const msg = (err && err.message) || '加载失败'
        const isDenied = /403|权限|管理员/.test(msg)
        that.setData({
          loading: false,
          denied: isDenied,
          error: isDenied ? '' : msg,
        })
      })
  },

  onRetry: function () {
    this.load()
  },
})
