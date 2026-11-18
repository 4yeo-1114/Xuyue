const api = require('../../utils/api')

// 试卷库：网页版「智能组卷」保存的试卷，与网页同一份数据。
// 选一份 → 「一键布置」把题目带去布置作业页直接生成作业纸。
Page({
  data: {
    loading: false,
    papers: [],
    error: '',
  },

  onShow: function () {
    if (!api.getToken()) {
      wx.reLaunch({ url: '/pages/login/login' })
      return
    }
    this.load()
  },

  onPullDownRefresh: function () {
    this.load().then(function () {
      wx.stopPullDownRefresh()
    })
  },

  load: function () {
    const that = this
    this.setData({ loading: true, error: '' })
    return api
      .listExamPapers()
      .then(function (papers) {
        // 接口已带 questions，整份留着供「一键布置」取用
        that._full = papers || []
        const rows = that._full.map(function (p) {
          return {
            id: p.id,
            title: p.title || '未命名试卷',
            subject: p.subject || '',
            count: (p.questions || []).length,
            updatedAt: (p.updatedAt || '').replace('T', ' ').slice(0, 16),
          }
        })
        that.setData({ papers: rows, loading: false })
      })
      .catch(function (err) {
        that.setData({
          loading: false,
          error: err.message || '试卷库加载失败',
        })
      })
  },

  onUse: function (e) {
    const id = e.currentTarget.dataset.id
    const full = (this._full || []).find(function (p) {
      return p.id === id
    })
    if (!full || !full.questions || !full.questions.length) {
      wx.showToast({ title: '这份试卷没有题目', icon: 'none' })
      return
    }
    wx.navigateTo({
      url:
        '/pages/index/index?paper=' +
        encodeURIComponent(
          JSON.stringify({
            title: full.title,
            subject: full.subject,
            questions: full.questions,
          }),
        ),
    })
  },
})
