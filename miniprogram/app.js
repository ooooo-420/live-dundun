// app.js
const { CLOUD_ENV, FONT_URL } = require('./utils/config')

App({
  onLaunch() {
    if (CLOUD_ENV && wx.cloud) {
      wx.cloud.init({ env: CLOUD_ENV, traceUser: false })
    }
    // 大號碼的展示字體：載不到就靜靜用系統字，頁面不受影響
    if (FONT_URL) {
      wx.loadFontFace({ family: 'LiveNum', global: true, source: `url("${FONT_URL}")`, fail: () => {} })
    }
  },
  globalData: {},
})
