const api = require('../../utils/api')
const config = require('../../utils/config')

Page({
  data: {
    appName: config.appName,
    email: '',
    password: '',
    loading: false,
  },

  onLoad: function () {
    // 已登录就不用再登
    if (api.getToken()) {
      wx.reLaunch({ url: '/pages/home/home' })
    }
  },

  onEmailInput: function (e) {
    this.setData({ email: e.detail.value })
  },

  onPasswordInput: function (e) {
    this.setData({ password: e.detail.value })
  },

  onSubmit: function () {
    const email = this.data.email.trim()
    const password = this.data.password

    if (!email) {
      wx.showToast({ title: '请输入账号', icon: 'none' })
      return
    }
    if (!password) {
      wx.showToast({ title: '请输入密码', icon: 'none' })
      return
    }

    const that = this
    this.setData({ loading: true })
    api
      .login(email, password)
      .then(function () {
        wx.showToast({ title: '登录成功', icon: 'success' })
        setTimeout(function () {
          wx.reLaunch({ url: '/pages/home/home' })
        }, 600)
      })
      .catch(function (err) {
        wx.showModal({
          title: '登录失败',
          content: err.message,
          showCancel: false,
        })
      })
      .then(function () {
        that.setData({ loading: false })
      })
  },
})
