# Config WebUI static files

这里放 `mms config web` / `mmz config web` 的前端资源，改 UI 时优先看这里，不需要打开 Python 后端文件。

- `index.html`：页面结构和文案区块。
- `config-web.css`：视觉样式、布局、响应式和 fixed 底部栏。
- `config-web.js`：浏览器交互、API 调用、渲染函数和表单状态。

Python 侧只负责：

- `mms_config_web_assets.py`：从本目录读取静态文件。
- `mms_config_web_server.py`：提供 `/static/config-web.css`、`/static/config-web.js` 和 WebUI API。
