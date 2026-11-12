// Copy to config.js and fill in your own cloud environment ID. config.js is not committed.
module.exports = {
  // 'cloud'：读写云开发数据库（要先部署云函数 api）；'demo'：示范数据，只存在手机本机
  MODE: 'cloud',
  CLOUD_ENV: 'cloud1-your-env-id',
  // 大号码的展示字体（选填）：把字体档上传到云开发“存储”，把它的 https 下载网址贴来。
  FONT_URL: '',
}
