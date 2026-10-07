# 未完成项台账

权威源是 `work-ledger.yaml`（AWR 的项目台账）；这份是给人看的一页纸：**还剩什么、为什么没做完、需要什么**。
每次收口时同步更新。

## 当前状态（2026-10-07）

60 个工作项：**completed 55 / ready 1 / planned 4**（本轮收掉 RTD-020、048、054、058 四项）。

| 项 | 状态 | 还差什么 | 需要谁 |
| --- | --- | --- | --- |
| **RTD-011** 真实执行器联调 | ready | 一台能访问目标平台的机器 + 账号；填 `.rtd/config.json` 后跑 `rtd-setup → rtd-env → rtd-dev` | **你**（提供环境） |
| RTD-009 回填工具 schema 快照 | planned | 依赖 RTD-011：拿真实回执回填，不许凭记忆写 | 你（同上） |
| RTD-010 回填九类数据源字段契约 | planned | 依赖 RTD-011：按平台界面或 CLI 帮助逐类核对 | 你（同上） |
| RTD-023 用真实窗口校准巡检阈值 | planned | 依赖 RTD-011：各取一个真实正常窗口与故障窗口做对照 | 你（同上） |
| RTD-015 定版与发布准备 | planned（**被依赖门挡住**） | 两条验收本轮都已满足（打包排除项干净、版本单源通过），但台账里它声明依赖 RTD-011，AWR 不允许在依赖未完成时收口 | **你**（决定是否放宽依赖，见下） |
| RTD-020 Claude 侧清单字段 | ✅ 本轮完成（**抓到真 bug**，见下） | — | — |
| RTD-048 / 054 / 058 三个组件的构件与真跑 | ✅ 本轮完成 | — | — |

一句话：**剩下的 5 项全部挂在 RTD-011 这条依赖链上**——它不是代码问题，是"需要能访问平台的环境"。
代码侧已经没有已知未完成项；RTD-015 的两条验收也过了，只差依赖门。

### 关于 RTD-015 的一个待你裁决

它的**验收**只有两条（打包排除项、版本单源），本轮都已核过；但**摘要与依赖**写着"等 RTD-011 与 RTD-014
有结论后再定版"。RTD-014 早完成了，RTD-011 的"结论"其实也已经有了——**结论就是"本机无法联调，按未验证呈现"**，
README 的边界表与 CHANGELOG 都是这么写的。

所以这里有两种同样诚实的走法，**由你定**：

* **收紧**（当前状态）：坚持"平台路径没验证就不定版"，那 RTD-015 跟着 RTD-011 一起等；
* **放宽**：认可"未验证也是一个结论"，把 RTD-015 的依赖从 RTD-011 上摘掉，它当场就能收口——
  代价是发布说明里必须继续明写"平台路径未验证"（现在是这么写的）。

我不替你改依赖：这个仓库自己的规矩是"不要为了解锁工作而标记前置完成/删除依赖"。

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
