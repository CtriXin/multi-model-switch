# v5.1.11 Preview · T9a 运行模块布局同步

同步 Stable 4.23.8 的 T9a：81 个运行模块（含 dev 独有的两个 Grok 模块）归入 `lib/`，入口、安装器与 Pilot 升级保持一致。保留 5.1.10 的 Bot、模型/Effort 交互与前端 bundle。

## 升级须知

- 旧平铺安装（包括 5.1.10）需先结束任务、退出 Pilot，再运行 Preview 安装器完成迁移。旧版 Pilot 内更新不能完成本次目录迁移。
- 安装器只按发行包精确文件名清理旧平铺模块，保留用户自建文件。
- 升级准备与安装阶段都会拒绝缺少 `lib/` 的旧包，防止跨线或旧缓存形成混合安装；拒绝前不会停止现有会话或替换安装。

```bash
curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/dev/install.sh | bash -s -- --channel dev
```

不更改用户模型、通道、API Key 或 Effort 默认值。本次没有前端源码变更，只同步版本与 source 摘要，资源 hash 不变。
