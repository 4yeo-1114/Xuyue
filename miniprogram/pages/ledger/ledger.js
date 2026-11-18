const api = require('../../utils/api')

const PAGE_SIZE = 20

// 来源分类中文名
const SOURCE_LABELS = {
  human_ai_correct: '人工改分',
  form_guard: '表单校验',
  vl_ink: '笔迹复核',
}

function sourceLabel(s) {
  return SOURCE_LABELS[s] || s || '其他'
}

Page({
  data: {
    q: '',
    source: '',
    days: 30,
    dayOptions: [7, 30, 90],
    sourceChips: [],
    rows: [],
    page: 1,
    hasMore: false,
    loading: false,
  },

  onLoad: function () {
    this.load(true)
  },

  onPullDownRefresh: function () {
    const that = this
    this.load(true).then(function () {
      wx.stopPullDownRefresh()
    })
  },

  onQueryInput: function (e) {
    this.setData({ q: e.detail.value })
  },

  onSearch: function () {
    this.load(true)
  },

  onSourceChip: function (e) {
    this.setData({ source: e.currentTarget.dataset.source || '' })
    this.load(true)
  },

  onDaysChip: function (e) {
    this.setData({ days: Number(e.currentTarget.dataset.days) || 30 })
    this.load(true)
  },

  onLoadMore: function () {
    if (this.data.loading || !this.data.hasMore) return
    this.load(false)
  },

  // reset=true 从第一页重来；false 追加下一页
  load: function (reset) {
    const that = this
    if (this.data.loading) return Promise.resolve()
    const page = reset ? 1 : this.data.page + 1
    this.setData({ loading: true })
    return api
      .getCorrectionLedger({
        days: this.data.days,
        source: this.data.source,
        q: this.data.q.trim(),
        page: page,
        page_size: PAGE_SIZE,
      })
      .then(function (data) {
        const incoming = ((data && data.rows) || []).map(function (r) {
          return Object.assign({}, r, {
            qLabel: r.sub_index != null && r.sub_index !== '' ? r.index + '.' + r.sub_index : r.index,
            wasLabel: that.rowChangeLabel(r, 'was'),
            newLabel: that.rowChangeLabel(r, 'new'),
            kindLabel: that.kindLabel(r),
            kindClass: that.kindClass(r),
            commentText: r.new_comment || r.was_comment || '',
            timeText: that.formatTime(r.created_at),
          })
        })
        // 分类 chip 计数（后端按当前窗口统计，含搜索/分类之外的过滤）
        const counts = (data && data.source_counts) || {}
        const chips = Object.keys(counts).map(function (k) {
          return { key: k, label: sourceLabel(k), count: counts[k] }
        })
        chips.sort(function (a, b) {
          return b.count - a.count
        })
        const rows = reset ? incoming : that.data.rows.concat(incoming)
        const total = (data && data.total) || 0
        that.setData({
          rows: rows,
          page: page,
          hasMore: rows.length < total,
          loading: false,
          sourceChips: chips,
        })
      })
      .catch(function (err) {
        that.setData({ loading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // 改动类型标签：判定/分/评语（有多项取前者）
  kindLabel: function (r) {
    if (r.was_result !== r.new_result) return '改判定'
    if (r.was_score !== r.new_score) return '改分'
    return '改评语'
  },

  kindClass: function (r) {
    if (r.was_result !== r.new_result) return 'tag-printing'
    if (r.was_score !== r.new_score) return 'tag-pending'
    return 'tag-draft'
  },

  // 前后值展示：判定优先，其次分数
  rowChangeLabel: function (r, which) {
    const res = which === 'was' ? r.was_result : r.new_result
    const score = which === 'was' ? r.was_score : r.new_score
    if (res && res !== (which === 'was' ? r.new_result : r.was_result)) return res
    if (score != null && score !== (which === 'was' ? r.new_score : r.was_score)) return score + ' 分'
    return res != null ? res : '—'
  },

  formatTime: function (iso) {
    if (!iso) return ''
    const d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    const pad = function (n) {
      return n < 10 ? '0' + n : '' + n
    }
    return (
      d.getFullYear() +
      '-' +
      pad(d.getMonth() + 1) +
      '-' +
      pad(d.getDate()) +
      ' ' +
      pad(d.getHours()) +
      ':' +
      pad(d.getMinutes())
    )
  },
})
