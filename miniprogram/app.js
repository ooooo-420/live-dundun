// app.js
const { CLOUD_ENV, FONT_URL } = require('./utils/config')

App({
  onLaunch() {
    if (CLOUD_ENV && wx.cloud) {
      wx.cloud.init({ env: CLOUD_ENV, traceUser: false })
    }
    // 大号码的展示字体：载不到就静静用系统字，页面不受影响
    if (FONT_URL) {
      wx.loadFontFace({ family: 'LiveNum', global: true, source: `url("${FONT_URL}")`, fail: () => {} })
    }
  },
  globalData: {},
})
