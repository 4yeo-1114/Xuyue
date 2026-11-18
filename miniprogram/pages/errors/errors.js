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
    folderItems: [],
    folderIndex: 0,
    loading: false,
    tab: 'questions', // questions | students
    stats: { student_count: 0, question_count: 0, error_rate: 0 },
    questions: [],
    students: [],
  },

  onLoad: function () {
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
        return that.loadFolders()
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
    this.loadFolders()
  },

  // 文件夹名形如 cls_<token>__显示名，展示时剥前缀
  loadFolders: function () {
    const that = this
    const cls = this.data.classes[this.data.classIndex]
    if (!cls) {
      this.setData({ folderItems: [], questions: [], students: [] })
      return Promise.resolve()
    }
    return api
      .listFolders(cls.id)
      .then(function (data) {
        const names = (data && data.folders) || []
        const items = names.map(function (name) {
          const parts = String(name).split('__')
          return { name: name, display: parts.length > 1 ? parts.slice(1).join('__') : name }
        })
        that.setData({ folderItems: items, folderIndex: 0 })
        return that.load()
      })
      .catch(function () {
        that.setData({ folderItems: [] })
      })
  },

  onClassChange: function (e) {
    this.setData({ classIndex: Number(e.detail.value) || 0 })
    this.loadFolders()
  },

  onFolderChange: function (e) {
    this.setData({ folderIndex: Number(e.detail.value) || 0 })
    this.load()
  },

  onTab: function (e) {
    this.setData({ tab: e.currentTarget.dataset.tab })
  },

  load: function () {
    const folder = this.data.folderItems[this.data.folderIndex]
    if (!folder) {
      this.setData({
        loading: false,
        stats: { student_count: 0, question_count: 0, error_rate: 0 },
        questions: [],
        students: [],
      })
      return Promise.resolve()
    }
    const that = this
    this.setData({ loading: true })
    return Promise.all([
      api.getErrorBookStats(folder.name),
      api.getErrorBookDetail(folder.name),
    ])
      .then(function (res) {
        const st = res[0] || {}
        const detail = res[1] || {}
        // 题目行预计算展示：错/空合计 + 错题名单文本
        const questions = (detail.questions || []).map(function (q) {
          return that.packQuestion(q, 0)
        })
        // 学生行：文件名当姓名显示（去扩展名），错题数进条形
        const maxWrong = Math.max.apply(
          null,
          (detail.students || []).map(function (s) {
            return s.wrong_count || 0
          }).concat([1])
        )
        const students = (detail.students || []).map(function (s) {
          const name = String(s.filename || '').replace(/\.[a-zA-Z0-9]+$/, '')
          return {
            name: name,
            score: s.score_total == null ? '—' : s.score_total,
            correct: s.correct_count || 0,
            wrong: s.wrong_count || 0,
            wrongPct: Math.round(((s.wrong_count || 0) / maxWrong) * 100),
            wrongText: (s.wrong_questions || []).slice(0, 6).join('、'),
          }
        })
        that.setData({
          loading: false,
          stats: {
            student_count: st.student_count || 0,
            question_count: st.question_count || 0,
            error_rate: st.error_rate || 0,
          },
          questions: questions,
          students: students,
        })
      })
      .catch(function (err) {
        that.setData({ loading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // 大题 + 子题递归打包（缩进层级预计算，模板不调函数）
  packQuestion: function (q, depth) {
    const that = this
    const wrong = q.wrong || 0
    const blank = q.blank || 0
    const correct = q.correct || 0
    const total = wrong + blank + correct || 1
    return {
      title: q.title || '（无题干）',
      depth: depth,
      indent: depth * 32,
      correct: correct,
      wrong: wrong,
      blank: blank,
      errRate: Math.round(((wrong + blank) / total) * 100),
      errPct: Math.round(((wrong + blank) / total) * 100),
      names: (q.wrong_students || []).join('、') || '—',
      subItems: (q.subItems || []).map(function (sub) {
        return that.packQuestion(sub, depth + 1)
      }),
    }
  },
})
