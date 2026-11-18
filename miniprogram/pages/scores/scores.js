const api = require('../../utils/api')
const classPicker = require('../../utils/classPicker')

// 考试文件夹名形如 cls_xxx__月考卷，展示时只留后半段
function folderDisplay(name) {
  const s = String(name || '')
  const i = s.indexOf('__')
  return i >= 0 ? s.slice(i + 2) : s
}

Page({
  data: {
    allClasses: [],
    gradeLabels: [],
    gradeIndex: 0,
    classes: [],
    classLabels: [],
    classIndex: 0,
    tab: 'scores',

    scoresLoading: false,
    folderItems: [],
    openFolder: '',
    rowsLoading: false,
    scoreRows: [],

    subjectLabels: [],
    subjectIndex: 0,
    radarLoading: false,
    dims: [],
  },

  onLoad: function () {
    this.loadClasses()
    this.loadSubjects()
  },

  onPullDownRefresh: function () {
    const that = this
    this.reloadCurrent().then(function () {
      wx.stopPullDownRefresh()
    })
  },

  // ── 班级 ──
  loadClasses: function () {
    const that = this
    this.setData({ scoresLoading: true })
    return api
      .listClasses()
      .then(function (rows) {
        const all = rows || []
        const grades = classPicker.gradeLabelsOf(all)
        that.setData({ allClasses: all, gradeLabels: grades, gradeIndex: 0 })
        that.applyGrade(grades[0])
        return that.reloadCurrent()
      })
      .catch(function (err) {
        that.setData({ scoresLoading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // 选年级 → 只列该年级的班，班级从头选
  applyGrade: function (grade) {
    const classes = classPicker.filterByGrade(this.data.allClasses, grade)
    const labels = classes.map(function (c) {
      return (c.grade || '') + (c.name || c.id)
    })
    this.setData({ classes: classes, classLabels: labels, classIndex: 0 })
  },

  onGradeChange: function (e) {
    const idx = Number(e.detail.value) || 0
    this.setData({ gradeIndex: idx, openFolder: '', scoreRows: [] })
    this.applyGrade(this.data.gradeLabels[idx])
    this.reloadCurrent()
  },

  onClassChange: function (e) {
    this.setData({ classIndex: Number(e.detail.value) || 0, openFolder: '', scoreRows: [] })
    this.reloadCurrent()
  },

  currentClassId: function () {
    const c = this.data.classes[this.data.classIndex]
    return c ? c.id : ''
  },

  // ── 切换 tab ──
  onTab: function (e) {
    const tab = e.currentTarget.dataset.tab
    if (tab === this.data.tab) return
    this.setData({ tab: tab })
    this.reloadCurrent()
  },

  reloadCurrent: function () {
    return this.data.tab === 'radar' ? this.loadRadar() : this.loadFolders()
  },

  // ── 成绩单 ──
  loadFolders: function () {
    const that = this
    const classId = this.currentClassId()
    if (!classId) {
      this.setData({ folderItems: [], scoresLoading: false })
      return Promise.resolve()
    }
    this.setData({ scoresLoading: true })
    return api
      .listFolders(classId)
      .then(function (res) {
        const meta = (res && res.meta) || {}
        const items = ((res && res.folders) || []).map(function (n) {
          const m = meta[n] || {}
          return {
            name: n,
            display: folderDisplay(n),
            subject: m.subject || '',
            grade: m.grade || '',
          }
        })
        that.setData({ folderItems: items, scoresLoading: false })
      })
      .catch(function (err) {
        that.setData({ scoresLoading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  onToggleFolder: function (e) {
    const folder = e.currentTarget.dataset.folder
    if (this.data.openFolder === folder) {
      this.setData({ openFolder: '', scoreRows: [] })
      return
    }
    this.setData({ openFolder: folder, scoreRows: [], rowsLoading: true })
    const that = this
    api
      .getScoreSummary(folder)
      .then(function (res) {
        const rows = ((res && res.rows) || []).map(function (r) {
          const max = Number(r.max_score) || 0
          const score = Number(r.score_total) || 0
          return Object.assign({}, r, {
            pct: max > 0 ? Math.min(100, Math.round((score / max) * 100)) : 0,
          })
        })
        that.setData({ scoreRows: rows, rowsLoading: false })
      })
      .catch(function (err) {
        that.setData({ rowsLoading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // ── 能力雷达 ──
  loadSubjects: function () {
    const that = this
    api
      .getSubjects()
      .then(function (rows) {
        const labels = (rows || []).map(function (s) {
          return typeof s === 'string' ? s : (s.label || s.value || '')
        })
        that.setData({ subjectLabels: labels, subjectIndex: 0 })
        if (that.data.tab === 'radar') that.loadRadar()
      })
      .catch(function () {
        // 科目拉不到就用最常见四科兜底，不挡雷达页
        that.setData({ subjectLabels: ['语文', '数学', '英语', '科学'], subjectIndex: 0 })
      })
  },

  onSubjectChange: function (e) {
    this.setData({ subjectIndex: Number(e.detail.value) || 0 })
    this.loadRadar()
  },

  loadRadar: function () {
    const that = this
    const classId = this.currentClassId()
    const subject = this.data.subjectLabels[this.data.subjectIndex] || ''
    if (!classId || !subject) {
      this.setData({ dims: [], radarLoading: false })
      return Promise.resolve()
    }
    this.setData({ radarLoading: true })
    return api
      .getClassReport(classId, subject)
      .then(function (data) {
        const raw =
          ((((data || {}).report || {}).analysis || {}).capability_dimensions || {}).dims || []
        // 与网页版同口径：有名且 score 为数字才算一维；条形按 0-100 归一
        const dims = raw
          .filter(function (d) {
            return d && d.name && typeof d.score === 'number'
          })
          .map(function (d) {
            const avg = typeof d.classAvg === 'number' ? d.classAvg : 0
            return {
              name: d.name,
              score: d.score,
              classAvg: avg,
              scorePct: Math.max(0, Math.min(100, d.score)),
              avgPct: Math.max(0, Math.min(100, avg)),
            }
          })
        that.setData({ dims: dims, radarLoading: false })
      })
      .catch(function (err) {
        that.setData({ dims: [], radarLoading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },
})
