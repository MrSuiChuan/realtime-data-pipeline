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

## 二、Codex：清单字段被接受，但 hook 未执行 ❌（待信任）

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

### 实测结论

```bash
codex exec -C <项目> -s workspace-write --skip-git-repo-check \
  --dangerously-bypass-hook-trust --json "用 shell 执行：echo hello > .rtd/_evidence/probe.json"
```

- 命令**执行成功**，文件被创建 → **没有被拦**；
- 用我们自己的 hook trace（`RTD_HOOK_TRACE`）验证：**trace 文件根本没生成** → 说明 hook 进程**一次都没被调用**（不是"调用了但放行"）。

即：在 `codex exec` 这条路径上，插件 hook 没有跑起来。信任记录目前只有 `ponytail` 与 `data-development-plugin` 的条目——那是**在 Codex 应用里被批准过**的钩子，说明正常路径是"应用内批准"。

### 下一步（一条人工动作）

在 Codex 应用里打开本插件，让它弹出 hook 信任提示并**批准**（`config.toml` 的 `[hooks.state]` 会出现 `realtime-data-plugin@personal:…` 条目）。批准后再跑一次上面的实验：预期是"被拒绝 + 文件不存在 + trace 里能看到 `PreToolUse` 载荷"。

### 已经改好的部分

- Codex 侧的 hook 文件独立成 `hooks/codex-hooks.json`（事件键与 Claude 一样是 PascalCase；`tools/adapt_hooks.py` 负责启动器适配），清单字段指向它；
- Claude 侧继续用自动发现的 `hooks/hooks.json`；
- 两边的协议实现共用同一份 `hooks/pretooluse.py`。
