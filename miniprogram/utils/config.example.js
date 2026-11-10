// Copy to config.js and fill in your own cloud environment ID. config.js is not committed.
module.exports = {
  // 'cloud'：讀寫雲開發資料庫（要先部署雲函數 api）；'demo'：示範資料，只存在手機本機
  MODE: 'cloud',
  CLOUD_ENV: 'cloud1-your-env-id',
  // 大號碼的展示字體（選填）：把字體檔上傳到雲開發「存儲」，把它的 https 下載網址貼來。
  FONT_URL: '',
}
