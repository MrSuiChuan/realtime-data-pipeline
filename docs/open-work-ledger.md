# 未完成项台账

权威源是 `work-ledger.yaml`（AWR 的项目台账）；这份是给人看的一页纸：**还剩什么、为什么没做完、需要什么**。
每次收口时同步更新。

## 当前状态（2026-10-07 收口完毕）

60 个工作项：**completed 55 / cancelled 5 / 没有 ready 或 planned**。

五个 **cancelled** 的项都终止在"本机验证不了"上，用的是 `cancel` 而不是 `complete`——
**没有拿完成来冒充通过**。要推进时用 `awr work reopen <id>` 重开即可。

| 项 | 终止原因 | 重开条件 |
| --- | --- | --- |
| **RTD-011** 真实执行器联调 | 本机与本次会话都没有可访问的目标平台环境；三条验收（env check 三态、真实编译回执过门、失败原文留档）一条都没做 | 一台能访问平台的机器 + 账号 |
| RTD-009 工具 schema 与字段契约回填 | 依赖的联调缺席，拿不到真实回执；保持"待回填"，不填推测内容 | 同上 |
| RTD-010 九类数据源字段契约 | 同上：必须按平台界面或 CLI 帮助逐类核对 | 同上 |
| RTD-023 巡检阈值校准 | 需要真实正常窗口与故障窗口做对照，本机没有这类数据 | 同上 |
| RTD-015 定版与发布准备 | 两条验收**已过**（打包排除项干净、版本单源通过），但它声明依赖 RTD-011，而该依赖无法完成 | 平台联调有结论后复核一次发布说明 |

一句话：**代码侧没有未完成项，剩下的五个都是环境问题**。README 与 CHANGELOG 里
"平台路径未经真实环境验证"的标注保持不变——收口不等于把未验证说成已验证。

## 本轮实际做完的三件事

### 1. Doris 真跑通过（RTD-058，连带 048 / 054）

前几轮卡在构件与内存。这一轮把四个前置凑齐后跑通：建库建表写 5 行读回 5 行，**连跑两次结果一致**：

| 前置 | 值 |
| --- | --- |
| 镜像入口要环境变量 | FE `FE_SERVERS=fe1:127.0.0.1:8030,FE_ID=1`；BE `FE_SERVERS=...` + `BE_ADDR=127.0.0.1:9050`（只写 IP 会报格式错） |
| 内核参数 | `vm.max_map_count` 必须**严格大于** 2000000（设成等于也拦） |
| 内存 | 必须关 swap（BE 自检），所以 FE 的默认 8GB 堆要降到 2GB |
| 会话 | 容器随发起会话结束被回收，前置与启动必须在**同一个 WSL 会话**里做完 |

为此给编排脚本加了通用的 `--fe-cmd` / `--be-cmd`（需要先改镜像内配置再启动时用），
并把"一次只起一个"的守卫修了：**端口重叠时不能靠端口判归属**（Doris 与 StarRocks 默认都用 9030）。

### 2. 定版与发布准备（RTD-015）

验收两条都过：打包产物不含 `plan.raw.md`、`.rtd/`、真实平台名（`git ls-files` 逐项核对 + 脱敏扫描零命中）；
版本单源校验通过（校验器第 5 项）。

### 3. **Claude Code 侧清单字段：抓到真 bug 并修掉**（RTD-020）

装上后在 Claude Code 里查，插件**根本没加载起来**：

```
> realtime-data-plugin@realtime-data-plugin
  Status: × failed to load
  Error: Hook load failed: Duplicate hooks file detected: ./hooks/hooks.json resolves to
         already-loaded file ...\hooks\hooks.json. The standard hooks/hooks.json is loaded
         automatically, so manifest.hooks should only reference additional hook files.
```

原因：Claude Code **自动加载** `hooks/hooks.json`，而清单里 `"hooks": "./hooks/hooks.json"` 又指了一次 →
重复 → 整个插件加载失败。**这个清单字段是自伤的**，去掉后立刻恢复：

```
> realtime-data-plugin@realtime-data-plugin
  Status: √ enabled
```

这正好印证了工作项里写的"无效则去掉字段并如实降级"——不用降级，是**去字段即修**。
`commands` 字段保留（未被报重复，且插件已正常加载）。

## 怎么用这份台账

1. 想看机器可读的权威状态：`awr intake inspect --project . --json`（带 `--source-sha <代码提交>` 看验证结论）；
2. 想接着做 RTD-011：按它的 next_action 准备环境与账号，其余四项会自动解锁；
3. 收口时把本文件与 `work-ledger.yaml` 一起更新——两处不一致时以 `work-ledger.yaml` 为准。
