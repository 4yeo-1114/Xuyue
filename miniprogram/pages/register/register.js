const api = require('../../utils/api')

// 全角→半角：手机中文输入法容易把邮箱/密码打成全角（＠１２３），服务端认不出来
function toHalfWidth(s) {
  return String(s || '')
    .replace(/[！-～]/g, function (c) {
      return String.fromCharCode(c.charCodeAt(0) - 0xfee0)
    })
    .replace(/　/g, ' ')
}

// 任教年级选项（选填），与网页版 buildGradeLevels 的取值一致
var GRADES = ['请选择任教年级', '一年级', '二年级', '三年级', '四年级', '五年级', '六年级', '七年级', '八年级', '九年级', '高一', '高二', '高三']

Page({
  data: {
    email: '',
    code: '',
    password: '',
    displayName: '',
    subject: '',
    grades: GRADES,
    gradeIndex: 0,
    loading: false,
    sendingCode: false,
    countdown: 0,
  },

  onUnload: function () {
    if (this._timer) clearInterval(this._timer)
  },

  onEmailInput: function (e) {
    this.setData({ email: e.detail.value })
  },

  onCodeInput: function (e) {
    this.setData({ code: e.detail.value })
  },

  onPasswordInput: function (e) {
    this.setData({ password: e.detail.value })
  },

  onNameInput: function (e) {
    this.setData({ displayName: e.detail.value })
  },

  onSubjectInput: function (e) {
    this.setData({ subject: e.detail.value })
  },

  onGradeChange: function (e) {
    this.setData({ gradeIndex: Number(e.detail.value) })
  },

  onSendCode: function () {
    const email = toHalfWidth(this.data.email).trim()
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      wx.showToast({ title: '请输入正确的邮箱', icon: 'none' })
      return
    }

    const that = this
    this.setData({ sendingCode: true })
    api
      .sendEmailCode(email)
      .then(function () {
        wx.showToast({ title: '验证码已发送', icon: 'success' })
        that.setData({ countdown: 60 })
        that._timer = setInterval(function () {
          const n = that.data.countdown - 1
          that.setData({ countdown: n })
          if (n <= 0) clearInterval(that._timer)
        }, 1000)
      })
      .catch(function (err) {
        wx.showModal({ title: '发送失败', content: err.message, showCancel: false })
      })
      .then(function () {
        that.setData({ sendingCode: false })
      })
  },

  onSubmit: function () {
    const email = toHalfWidth(this.data.email).trim()
    const password = toHalfWidth(this.data.password)
    const code = String(this.data.code || '').trim()

    if (!/^\S+@\S+\.\S+$/.test(email)) {
      wx.showToast({ title: '请输入正确的邮箱', icon: 'none' })
      return
    }
    if (password.length < 6) {
      wx.showToast({ title: '密码至少 6 位', icon: 'none' })
      return
    }
    if (!code) {
      wx.showToast({ title: '请输入验证码', icon: 'none' })
      return
    }

    // 角色固定「任课教师」（与网页版一致，防公网自封管理员）
    const payload = {
      email: email,
      password: password,
      email_code: code,
      role: '任课教师',
    }
    if (this.data.displayName.trim()) payload.display_name = this.data.displayName.trim()
    if (this.data.subject.trim()) payload.teaching_subject = this.data.subject.trim()
    if (this.data.gradeIndex > 0) payload.teaching_grade = this.data.grades[this.data.gradeIndex]

    const that = this
    this.setData({ loading: true })
    api
      .register(payload)
      .then(function () {
        wx.showToast({ title: '注册成功', icon: 'success' })
        setTimeout(function () {
          wx.reLaunch({ url: '/pages/home/home' })
        }, 600)
      })
      .catch(function (err) {
        // 服务端原文透出（已注册/频繁/验证码/科目超长等），用户才知道该改哪里
        wx.showModal({ title: '注册失败', content: err.message, showCancel: false })
      })
      .then(function () {
        that.setData({ loading: false })
      })
  },

  onGoLogin: function () {
    wx.navigateBack({
      fail: function () {
        wx.reLaunch({ url: '/pages/login/login' })
      },
    })
  },
})
