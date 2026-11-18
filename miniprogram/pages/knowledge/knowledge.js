const api = require('../../utils/api')
const seedData = require('../../utils/knowledgeSeedData')

Page({
  data: {
    subjectLabels: ['语文', '数学', '英语', '科学', '物理', '化学', '生物', '历史', '地理', '政治'],
    subjectIndex: 0,
    termLabels: ['上学期', '下学期'],
    termIndex: 0,
    loading: true,
    seeding: false,
    units: [], // [{id,name,subtitle,kps:[{...含详情字段}]}]
    showDetail: false,
    detail: null,
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

  onSubjectChange: function (e) {
    this.setData({ subjectIndex: Number(e.detail.value) || 0 })
    this.load()
  },

  onTermChange: function (e) {
    this.setData({ termIndex: Number(e.detail.value) || 0 })
    this.load()
  },

  load: function () {
    const that = this
    const subject = this.data.subjectLabels[this.data.subjectIndex]
    const semester = this.data.termLabels[this.data.termIndex]
    this.setData({ loading: true, showDetail: false })
    return api
      .getKnowledgeData(subject, semester)
      .then(function (data) {
        const kps = (data && data.kps) || []
        const byUnit = {}
        kps.forEach(function (k) {
          const key = k.unit_id || ''
          if (!byUnit[key]) byUnit[key] = []
          byUnit[key].push({
            code: k.code || '',
            name: k.name || '',
            level: k.level || '',
            mastery: k.mastery == null ? '—' : k.mastery,
            // mastery 是 0-1 或 0-100 两种历史口径都见过，>1 当百分数用
            masteryPct: k.mastery == null ? 0 : Math.round(k.mastery > 1 ? k.mastery : k.mastery * 100),
            isWeak: !!k.is_weak,
            hours: k.hours == null ? '' : k.hours,
            keyPoint: k.key_point || '',
            difficulty: k.difficulty || '',
            commonErrors: k.common_errors || '',
            prerequisite: k.prerequisite || [],
            postrequisite: k.postrequisite || [],
            related: k.related || [],
            resources: k.resources || [],
          })
        })
        const units = ((data && data.units) || []).map(function (u) {
          return {
            id: u.id,
            name: u.name || '',
            subtitle: u.subtitle || '',
            kps: byUnit[u.id] || [],
          }
        })
        // 单元可能整体缺失（只有孤儿 kps）时兜底归组
        if (units.length === 0 && kps.length > 0) {
          units.push({ id: '', name: '知识点', subtitle: '', kps: byUnit[''] || [] })
        }
        that.setData({ loading: false, units: units })
      })
      .catch(function (err) {
        that.setData({ loading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // 点知识点 → 详情卡（常见错误/难度/前置后续/相关/资料）
  onKpTap: function (e) {
    const uIdx = Number(e.currentTarget.dataset.u)
    const kIdx = Number(e.currentTarget.dataset.k)
    const unit = this.data.units[uIdx]
    const kp = unit && unit.kps[kIdx]
    if (!kp) return
    this.setData({
      showDetail: true,
      detail: Object.assign({ unitName: unit.name }, kp),
    })
  },

  onCloseDetail: function () {
    this.setData({ showDetail: false })
  },

  noop: function () {},

  // 空数据时一键初始化：导入内置课程知识点（与网页版「学科配置」初始化同源）
  onInitData: function () {
    const that = this
    if (this.data.seeding) return
    const subject = this.data.subjectLabels[this.data.subjectIndex]
    const semester = this.data.termLabels[this.data.termIndex]
    const cfg = seedData.getSubjectConfig(subject)
    if (!cfg.units.length) {
      wx.showToast({ title: '该学科暂无内置演示数据', icon: 'none' })
      return
    }
    this.setData({ seeding: true })
    const units = cfg.units.map(function (u) {
      return {
        unit_index: u.index,
        name: u.name,
        subtitle: u.subtitle || '',
        knowledgePoints: u.knowledgePoints.map(function (kp) {
          return {
            code: kp.code,
            name: kp.name,
            level: kp.level,
            mastery: kp.mastery,
            is_weak: kp.isWeak,
            prerequisite: kp.prerequisite,
            postrequisite: kp.postrequisite,
            related: kp.related,
            hours: kp.hours,
            key_point: kp.keyPoint,
            difficulty: kp.difficulty,
            common_errors: kp.commonErrors,
            resources: kp.resources,
          }
        }),
      }
    })
    api
      .seedKnowledgeData(subject, semester, units)
      .then(function () {
        that.setData({ seeding: false })
        wx.showToast({ title: '已导入知识点', icon: 'success' })
        that.load()
      })
      .catch(function (err) {
        that.setData({ seeding: false })
        wx.showToast({ title: err.message || '初始化失败', icon: 'none' })
      })
  },
})
