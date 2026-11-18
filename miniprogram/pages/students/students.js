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
    students: [],
    loading: true,
    // 展开的学生档案
    openName: '',
    profileLoading: false,
    profile: null, // { target, history:[{exam,score,avg,scorePct,avgPct,up}], wrongExam, wrongs:[{title,kp,img,ans}], alerts:[] }
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
    this.setData({ gradeIndex: idx, openName: '', profile: null })
    this.applyGrade(this.data.gradeLabels[idx])
    this.load()
  },

  loadSubjects: function () {
    const that = this
    api
      .getSubjects()
      .then(function (rows) {
        that.setData({ subjectLabels: rows || ['语文', '数学', '英语', '科学'], subjectIndex: 0 })
        if (that.data.classLabels.length) that.load()
      })
      .catch(function () {
        that.setData({ subjectLabels: ['语文', '数学', '英语', '科学'], subjectIndex: 0 })
        if (that.data.classLabels.length) that.load()
      })
  },

  onClassChange: function (e) {
    this.setData({ classIndex: Number(e.detail.value) || 0, openName: '', profile: null })
    this.load()
  },

  onSubjectChange: function (e) {
    this.setData({ subjectIndex: Number(e.detail.value) || 0, openName: '', profile: null })
    this.load()
  },

  load: function () {
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

  // 展开某生档案：成绩走势 + 最近错题 + 趋势预警
  onToggleStudent: function (e) {
    const name = e.currentTarget.dataset.name
    if (this.data.openName === name) {
      this.setData({ openName: '', profile: null })
      return
    }
    const that = this
    const cls = this.data.classes[this.data.classIndex]
    const subject = this.data.subjectLabels[this.data.subjectIndex] || ''
    const student = (this.data.students || []).find(function (s) {
      return s.name === name
    })
    this.setData({ openName: name, profileLoading: true, profile: null })

    const jobs = [
      api.getScoreHistory(cls.id, name, subject),
      api.getStudentWrongQuestions(cls.id, name, subject),
    ]
    if (student && student.id) {
      jobs.push(api.getTrendAlerts(student.id, cls.id))
    } else {
      jobs.push(Promise.resolve({ alerts: [] }))
    }

    Promise.all(jobs)
      .then(function (res) {
        const history = (res[0] || []).map(function (h, i, arr) {
          const max = Math.max(h.score || 0, h.class_avg || 0, 1)
          const prev = i > 0 ? arr[i - 1].score : null
          return {
            exam: h.exam_name || '考试',
            score: h.score,
            avg: h.class_avg == null ? '—' : h.class_avg,
            scorePct: Math.round(((h.score || 0) / max) * 100),
            avgPct: Math.round(((h.class_avg || 0) / max) * 100),
            up: prev == null ? '' : h.score > prev ? '↑' : h.score < prev ? '↓' : '→',
          }
        })
        const wq = res[1] || {}
        const wrongs = (wq.questions || []).map(function (q) {
          return {
            title: q.title || '',
            kp: q.knowledge_point_name || '',
            img: api.resolveFileUrl(q.image_url || ''),
            ans: api.resolveFileUrl(q.answer_url || ''),
          }
        })
        const alerts = ((res[2] && res[2].alerts) || []).map(function (a) {
          return {
            level: a.level || 'info',
            levelLabel: a.level === 'warn' ? '注意' : a.level === 'danger' ? '预警' : '提示',
            text: a.message || a.text || JSON.stringify(a),
          }
        })
        that.setData({
          profileLoading: false,
          profile: {
            history: history,
            wrongExam: wq.exam_name || '',
            wrongs: wrongs,
            alerts: alerts,
          },
        })
      })
      .catch(function (err) {
        that.setData({ profileLoading: false })
        wx.showToast({ title: err.message, icon: 'none' })
      })
  },

  // 点图看大图
  onPreview: function (e) {
    const url = e.currentTarget.dataset.url
    const urls = (this.data.profile.wrongs || [])
      .map(function (w) {
        return w.img
      })
      .filter(Boolean)
    if (!url) return
    wx.previewImage({ current: url, urls: urls.length ? urls : [url] })
  },
})
