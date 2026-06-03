# Config WebUI static files

这里放 `mms config web` / `mmz config web` 的前端资源，改 UI 时优先看这里，不需要打开 Python 后端文件。

- `index.html`：页面结构和文案区块。
- `config-web.css`：视觉样式、布局、响应式和 fixed 底部栏。
- `config-web.js`：浏览器交互、API 调用、渲染函数和表单状态。

当前设置页采用 WebUI-first 拆分：

- 设置首页只做模块导航和少量全局偏好。
- 通道、模型能力、Skill/MCP/Hook、Runtime、Fallback、迁移、保存审计分别在独立 section 里维护。
- TUI Settings 只保留通道快调、语言、rescue 和高级/应急入口；完整设置默认回到 WebUI。

Python 侧只负责：

- `mms_config_web_assets.py`：从本目录读取静态文件。
- `mms_config_web_server.py`：提供 `/static/config-web.css`、`/static/config-web.js` 和 WebUI API。
