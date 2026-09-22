# 宿主 hook 实测记录

硬门是不是真的硬，只能在宿主里试。本文件记录两个宿主的实测过程与结论，所有说法都有命令与输出支撑。

## 一、Claude Code：已实测生效 ✅

环境：Claude Code 2.1.231（`~/.claude` 下已装多套插件）。

### 安装

仓库自带 Claude Code 的 marketplace 清单 `.claude-plugin/marketplace.json`，所以能直接从本地目录装：

```bash
claude plugin marketplace add "C:\Users\wuzongyun\Documents\ChatGPT\realtime-data-plugin"
claude plugin install realtime-data-plugin@realtime-data-plugin
```

### 组件清单直接给出答案

```bash
claude plugin details realtime-data-plugin@realtime-data-plugin
```

```
Hooks (2)  PreToolUse, SessionStart  (harness-only — no model context cost)
```

### 端到端触发（关键证据）

在已初始化的项目里跑非交互会话：

```bash
claude -p "请用 Bash 工具执行这条命令…：echo hello > .rtd/_evidence/probe.json" --allowedTools Bash
```

| 用例 | 结果 |
| --- | --- |
| 对照：`echo hi > /tmp/rtd-probe-ok.txt` | 正常执行，exit 0 |
| 实验：`echo hello > .rtd/_evidence/probe.json` | **被拒绝**，且文件**未创建** |

拒绝原因原文（就是我们的门在说话）：

```
[realtime-data-plugin:evidence_write] 工具调用被硬门拦截。证据与状态文件（.rtd/_evidence/、_state.json）
只能由引擎写。要用 rtd.py evidence add / gate set / advance 提交，不要直接改文件。
```

### 附带发现

- Claude Code **按约定自动发现 `hooks/hooks.json`**；官方插件（如 `security-guidance`）有该文件但清单里**不声明** `hooks` 字段，说明字段不是必需的；
- 插件里的 `commands/*.md` 与 `skills/rtd-*/SKILL.md` **两边都会加载**（组件清单里 26 个），后者是给 Codex 用的生成物，在 Claude 侧属于重复（约 694 token always-on）。这是一处可优化点，尚未处理。

## 二、Codex：会话里会跑，`codex exec` 不跑（已用对照实验定论）

环境：Codex CLI（`codex plugin` / `codex exec`），插件通过个人 marketplace 装入。

### 从二进制里读出来的事实

| 事实 | 证据 |
| --- | --- |
| 支持插件清单的 `hooks` 字段 | 二进制含 `plugin.json#hooks`，且我们填了以后原先的告警消失 |
| 会自动发现 `hooks/hooks.json` | 二进制含字面量 `hooks/hooks.json` |
| 输出协议与 Claude 兼容 | 二进制含 `hookSpecificOutput`、`hookEventName`、`permissionDecision: deny`、`tool_name`、`tool_input` |
| 事件名在内部规范化成 snake_case | 配置里信任键写作 `…:pre_tool_use:0:0`、`…:session_start:0:0` |
| **hook 需要"信任"才会执行** | `config.toml` 的 `[hooks.state]` 按 `插件@市场:文件:事件:索引:索引` 记 `trusted_hash`；二进制含 `--dangerously-bypass-hook-trust`、`Trust to view hooks` 等文案 |
| CLI 有绕过开关 | `--dangerously-bypass-hook-trust`：Run enabled hooks without requiring persisted hook trust for this invocation |

### 关键：`codex exec` 不跑插件 hook（用对照实验证明）

第一次测试我得出"hook 没被调用"的结论，但那个测试本身是**无效的**——需要一个已信任的插件做对照才能定论。

| 实验 | 结果 |
| --- | --- |
| `codex exec` 里让 ddp（**已信任**的插件）去写它自己 guard 的 `.data-dev/runtime/` | 写入**成功**，没被拦 → **exec 模式不跑插件 hook** |
| 本次桌面会话里，让 ddp 去写同一路径 | **被拦**（原文：`Command blocked by PreToolUse hook: [data-development-plugin:runtime_guard] …`） |
| 本次会话里 patch 里出现 `.data-dev/runtime` 字样 | **同样被拦**（说明它连 apply_patch 的 payload 也看） |

结论：**hook 在 Codex 桌面会话里是生效的**（ddp 就是活证据），`codex exec` 这条 CLI 路径不加载插件 hook。所以之前那次"我们的 hook 没跑"不能推出"信任没批"。

### 本插件为什么在当前会话里没生效

插件是在**当前会话开始之后**才安装的，会话启动时已经加载完插件列表：

```
在项目里写 .rtd/_evidence/probe-session.json  → 写入成功（本会话未加载本插件）
同时 ddp 的 hook 能拦住同会话的其它写入        → 钩子机制本身是活的
```

### 下一步（一条人工动作：开一个新会话）

**新开一个 Codex 会话**（新会话才会加载刚装的插件）。加载时若出现 hook 信任提示就批准；判据是 `~/.codex/config.toml` 的 `[hooks.state]` 里出现本插件条目：

```toml
[hooks.state."realtime-data-plugin@personal:hooks/codex-hooks.json:pre_tool_use:0:0"]
trusted_hash = "sha256:…"
[hooks.state."realtime-data-plugin@personal:hooks/codex-hooks.json:session_start:0:0"]
trusted_hash = "sha256:…"
```

（现在这些条目只有 `ponytail` / `data-development-plugin` / `knowledge-base-plugin`——说明这个提示确实出现过、你当时批准过；本插件还没被任何新会话加载过，所以没提示。）

然后在新会话里跑一次实验：写入 `.rtd/_evidence/` → 预期"被拒绝 + 文件不存在"。

### 已经改好的部分

- Codex 侧的 hook 文件独立成 `hooks/codex-hooks.json`（事件键与 Claude 一样是 PascalCase；`tools/adapt_hooks.py` 负责启动器适配），清单字段指向它；
- Claude 侧继续用自动发现的 `hooks/hooks.json`；
- 两边的协议实现共用同一份 `hooks/pretooluse.py`。
