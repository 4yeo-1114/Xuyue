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
    students: [],
    loading: true,
    showAdd: false,
    addName: '',
    addNumber: '',
    addGender: '男',
    genderLabels: ['男', '女', '未知'],
    genderIndex: 0,
    saving: false,
  },

  onLoad: function () {
    this.loadClasses()
  },

  onPullDownRefresh: function () {
    const that = this
    this.loadStudents().then(function () {
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
        return that.loadStudents()
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
      return (c.grade || '') + (c.name || c.id) + '（' + (c.student_count || 0) + '人）'
    })
    this.setData({ classes: classes, classLabels: labels, classIndex: 0 })
  },

  onGradeChange: function (e) {
    const idx = Number(e.detail.value) || 0
    this.setData({ gradeIndex: idx })
    this.applyGrade(this.data.gradeLabels[idx])
    this.loadStudents()
  },

  onClassChange: function (e) {
    this.setData({ classIndex: Number(e.detail.value) || 0 })
    this.loadStudents()
  },

  loadStudents: function () {
    const that = this
    const cls = this.data.classes[this.data.classIndex]
    if (!cls) {
      this.setData({ loading: false, students: [] })
      return Promise.resolve()
    }
    this.setData({ loading: true })
    return api
      .listStudents(cls.id)
      .then(function (rows) {
        that.setData({ loading: false, students: rows || [] })
      })
      .catch(function (err) {
        that.setData({ loading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // ── 新增学生 ──
  onOpenAdd: function () {
    this.setData({ showAdd: true, addName: '', addNumber: '', genderIndex: 0 })
  },

  onCloseAdd: function () {
    this.setData({ showAdd: false })
  },

  onNameInput: function (e) {
    this.setData({ addName: e.detail.value })
  },

  onNumberInput: function (e) {
    this.setData({ addNumber: e.detail.value })
  },

  onGenderChange: function (e) {
    this.setData({ genderIndex: Number(e.detail.value) || 0 })
  },

  onSaveStudent: function () {
    const that = this
    const cls = this.data.classes[this.data.classIndex]
    const name = (this.data.addName || '').trim()
    if (!cls || !name) {
      wx.showToast({ title: '请填写学生姓名', icon: 'none' })
      return
    }
    this.setData({ saving: true })
    api
      .createStudent({
        class_id: cls.id,
        name: name,
        student_number: (this.data.addNumber || '').trim(),
        gender: this.data.genderLabels[this.data.genderIndex],
      })
      .then(function () {
        that.setData({ saving: false, showAdd: false })
        wx.showToast({ title: '已添加', icon: 'success' })
        that.loadClasses()
      })
      .catch(function (err) {
        that.setData({ saving: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // ── 删除学生 ──
  onDeleteStudent: function (e) {
    const index = Number(e.currentTarget.dataset.index)
    const stu = this.data.students[index]
    if (!stu) return
    const that = this
    wx.showModal({
      title: '删除学生',
      content: '确定删除「' + stu.name + '」吗？其成绩记录不受影响。',
      success: function (res) {
        if (!res.confirm) return
        api
          .deleteStudent(stu.id)
          .then(function () {
            wx.showToast({ title: '已删除', icon: 'success' })
            that.loadClasses()
          })
          .catch(function (err) {
            wx.showToast({ title: err.message, icon: 'none' })
          })
      },
    })
  },

  noop: function () {},
})
