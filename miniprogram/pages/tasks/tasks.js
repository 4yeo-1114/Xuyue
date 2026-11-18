const api = require('../../utils/api')
const classPicker = require('../../utils/classPicker')

Page({
  data: {
    allClasses: [],
    gradeLabels: [],
    gradeIndex: 0,
    classes: [],
    classLabels: [],
    classIndex: 0,
    subjectLabels: [],
    subjectIndex: 0,
    loading: true,
    tasks: [],
    total: 0,
    done: 0,
    progressPct: 0,
  },

  onLoad: function () {
    this.loadSubjects()
    this.loadClasses()
  },

  onPullDownRefresh: function () {
    const that = this
    this.load().then(function () {
      wx.stopPullDownRefresh()
    })
  },

  loadClasses: function () {
    const that = this
    return api
      .listClasses()
      .then(function (rows) {
        const all = rows || []
        const grades = classPicker.gradeLabelsOf(all)
        that.setData({ allClasses: all, gradeLabels: grades, gradeIndex: 0 })
        that.applyGrade(grades[0])
        return that.load()
      })
      .catch(function (err) {
        that.setData({ loading: false })
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
    this.setData({ gradeIndex: idx })
    this.applyGrade(this.data.gradeLabels[idx])
    this.load()
  },

  loadSubjects: function () {
    const that = this
    api
      .getSubjects()
      .then(function (rows) {
        that.setData({
          subjectLabels: rows || ['语文', '数学', '英语', '科学'],
          subjectIndex: 0,
        })
        // 科目可能比班级晚到：到齐就补拉一次任务
        if (that.data.classLabels.length) that.load()
      })
      .catch(function () {
        that.setData({ subjectLabels: ['语文', '数学', '英语', '科学'], subjectIndex: 0 })
        if (that.data.classLabels.length) that.load()
      })
  },

  onClassChange: function (e) {
    this.setData({ classIndex: Number(e.detail.value) || 0 })
    this.load()
  },

  onSubjectChange: function (e) {
    this.setData({ subjectIndex: Number(e.detail.value) || 0 })
    this.load()
  },

  load: function () {
    const that = this
    const cls = this.data.classes[this.data.classIndex]
    const subject = this.data.subjectLabels[this.data.subjectIndex] || ''
    if (!cls || !subject) {
      this.setData({ loading: false, tasks: [], total: 0, done: 0, progressPct: 0 })
      return Promise.resolve()
    }
    this.setData({ loading: true })
    return api
      .listImprovementTasks(cls.id, subject)
      .then(function (data) {
        const tasks = (data && data.tasks) || []
        const total = (data && data.total) || tasks.length
        const done = (data && data.done) || 0
        that.setData({
          tasks: tasks,
          total: total,
          done: done,
          progressPct: total > 0 ? Math.round((done / total) * 100) : 0,
          loading: false,
        })
      })
      .catch(function (err) {
        that.setData({ loading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // 勾/取消任务完成。乐观更新，失败回滚。
  onToggle: function (e) {
    const index = Number(e.currentTarget.dataset.index)
    const task = this.data.tasks[index]
    if (!task) return
    const that = this
    const was = !!task.is_done
    const key = 'tasks[' + index + '].is_done'
    this.setData({
      [key]: !was,
      done: this.data.done + (was ? -1 : 1),
    })
    this.setData({
      progressPct:
        this.data.total > 0 ? Math.round((this.data.done / this.data.total) * 100) : 0,
    })
    api.updateImprovementTask(task.id, !was).catch(function (err) {
      that.setData({
        [key]: was,
        done: that.data.done + (was ? 1 : -1),
      })
      that.setData({
        progressPct:
          that.data.total > 0 ? Math.round((that.data.done / that.data.total) * 100) : 0,
      })
      wx.showToast({ title: err.message, icon: 'none' })
    })
  },
})
