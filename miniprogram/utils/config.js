// 小程序設定。環境 ID 不是密碼，可以放在程式碼裡；AppSecret 絕對不要放進小程序。
module.exports = {
  // 'cloud'：讀寫雲開發資料庫（要先部署雲函數 api）；'demo'：示範資料，只存在手機本機
  MODE: 'cloud',
  CLOUD_ENV: 'cloud1-your-env-id',
  // 大號碼的展示字體（選填）：把字體檔上傳到雲開發「存儲」，把它的 https 下載網址貼來。
  // 空字串＝用手機系統字。網址的網域要在小程序後台 downloadFile 合法域名裡。
  FONT_URL: '',
}
