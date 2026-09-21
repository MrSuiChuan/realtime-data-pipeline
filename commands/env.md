# rtd-env — 执行器环境检查与接入

流程见 `workflows/runbook-environment.md`；接入纪律见 `governance/mcp-setup.md`。

## 三个模式

| 用户说 | 模式 | 行为 |
| --- | --- | --- |
| 检查 | check | 只查不装 |
| 安装/初始化 | install | 跳过已装的 |
| 更新 | update | 仅当明确有可用更新 |

```
py -3 .rtd/engine/rtd.py env check --json
```

## 三种状态别混

`配置存在` / `认证完成` / **当前会话可调用**——只有第三种算可用。引擎不做平台调用，认证与可调用要靠一次真实只读请求。

## CLI 缺能力时

先问要不要升级；拒绝升级再按 `governance/executor-arbitration.md` 评估有界回退。**不自动切换执行器**；版本号不是判据，帮助正文才是。
