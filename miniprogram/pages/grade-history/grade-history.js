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
    items: [],
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
      .listGradeHomeRecent()
      .then(function (res) {
        const items = (res.items || []).map(function (it) {
          return Object.assign({}, it, {
            statusText: STATUS_TEXT[it.status] || it.status,
            timeText: that.formatTime(it.created_at),
          })
        })
        that.setData({ items: items, loading: false })
      })
      .catch(function (err) {
        that.setData({ error: err.message, loading: false })
      })
  },

  formatTime: function (iso) {
    if (!iso) return ''
    const d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    const pad = function (n) { return n < 10 ? '0' + n : '' + n }
    return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
  },

  onTapItem: function (e) {
    const it = this.data.items[e.currentTarget.dataset.index]
    wx.navigateTo({ url: '/pages/grade/grade?jobId=' + it.id })
  },

  onDelete: function (e) {
    const idx = e.currentTarget.dataset.index
    const it = this.data.items[idx]
    const that = this
    wx.showModal({
      title: '删除记录',
      content: '删除后这条批改记录和留痕图都会清掉，确定吗？',
      success: function (res) {
        if (!res.confirm) return
        api
          .deleteGradeHome(it.id)
          .then(function () {
            wx.showToast({ title: '已删除', icon: 'success' })
            that.load()
          })
          .catch(function (err) {
            wx.showModal({ title: '删除失败', content: err.message, showCancel: false })
          })
      },
    })
  },
})
