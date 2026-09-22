# realtime-data-plugin

把实时数据任务的研发工艺翻成**状态机 + 硬门控**：AI 在门内自己干活，阶段出口只认机器证据。

## 它解决什么问题

实时任务开发的坑不在"会不会写 SQL"，而在三件事上：

1. **证据不实**：编译"看起来过了"、发布"应该成功了"、调试"没报错"，然后线上发现表没数据；
2. **确认失效**：一次同意被当成一路放行，启动、回刷、下线这些改线上状态的动作没有当次确认；
3. **状态丢失**：换个会话接着干，对象 ID、版本、追踪 ID 全凭记忆，重发一次写操作就是事故。

本插件把这三件事变成机制：阶段出口有门控键、门控键只能由引擎按证据写入、证据落盘可核验、续跑先回读平台真实状态。

## 三层结构

| 层 | 目录 | 作用 |
| --- | --- | --- |
| 规制层 | `governance/` | 安全宪法（门禁与只读边界）、执行器仲裁、身份与时间、输出契约、反例库、能力矩阵 |
| 工作流层 | `workflows/` | 十份 runbook：定位、研发、迁移、元表、启停、巡检、诊断、调参、环境、衔接总图 |
| 执行器层 | `executors/` + 项目级 `.rtd/config.json` | 命令与工具契约；真实命令名/MCP 服务名只在配置里 |

## 执行器与脱敏

仓库内**不含任何平台专有名**。平台 CLI 命令名、各域 MCP 服务名、存储分支工具名，以及巡检预算、轮询节奏等限额，全部从项目级 `.rtd/config.json` 读取（该文件不进仓库、不进发布包，权限 0600）。

配置缺项时的行为是**报缺口并停**：不猜命令名、不自动安装、不自动切换到另一个执行器。

## 快速开始（目标形态）

> 下面的命令是本插件全部阶段落地后的用法。现在仓库还在骨架阶段，`commands/` 与 `skills/` 尚未生成，照此执行会找不到入口——进度见下一节的表。

```bash
# 1) 装插件：从本仓库目录加载（两宿主共用同一引擎与 hook）
#    Claude Code:  marketplace 指向本仓库根目录
#    Codex:        把本仓库路径加进插件来源后重载

# 2) 在项目里初始化运行时并接入你的平台
/rtd-setup          # Claude Code；Codex 侧入口是技能 rtd-setup

# 3) 开工
/rtd-dev "把这两张实时表做成一条宽表任务，10 秒聚合"
```

初始化会创建 `<项目>/.rtd/`（状态、证据、执行记录）并生成 `config.json` 模板；填好执行器后 `rtd-status` 会列出当前还缺哪一项。

执行器有两条路，选一条配全即可：**平台路径**（平台 CLI + 各域 MCP）或**开源路径**（Flink / Paimon / Fluss，三段 `oss_*` 都要填）。`rtd-env` 分别判定，不会拿另一条路的要求来报缺口。

## 现在到哪一步

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Q0 | 设计源与优化（`plan.md`） | ✅ |
| Q1 | 仓库骨架、双宿主清单、CI、脱敏词表 | ✅ |
| Q2 | 规制层 7 件（宪法/仲裁/身份时间/输出契约/反例库/接入/能力矩阵） | ✅ |
| Q3 | 工作流层：12 个命令入口 + 11 份工作流文档 | ✅ |
| Q4 | 执行器契约 5 份 + 配置层（`templates/config.example.json`） | ✅（schema 快照待回填） |
| Q5 | 数据源层：生命周期 + 类型槽位 | ✅（字段契约待回填） |
| Q6 | 知识层 3 件 + 出站路由映射 | ✅ |
| Q7 | 引擎 `engine/rtd.py` + hooks 硬门控 | ✅ |
| Q8 | evals 五组 + 八项静态校验 | ✅（定版与真实平台联调待做） |
| Q9 | 巡检评分脚本（离线出报告，不碰网络、不覆盖历史） | ✅（阈值待真实窗口校准） |

本地自检（当前全绿）：

```bash
py -3 tools/build_codex_surface.py --check   # 生成物与命令源一致
py -3 tools/adapt_hooks.py --check            # hook 启动器与平台一致
py -3 tools/validate_plugin.py .             # 八项静态校验（含脱敏扫描）
py -3 tests/test_engine.py                   # 引擎：门控/证据/阶段/续跑
py -3 tests/test_hooks.py                    # hook：三条硬规则的正负例
py -3 tests/test_score_inspection.py         # 巡检评分：出报告 + 拦住四类坏输入
py -3 tests/test_repo_invariants.py          # 仓库不变量
py -3 tools/awr_reports.py                    # 台账验收报告：每个工作项最新一轮是哪个提交
```

## 引擎怎么用（一步到位的样子）

```bash
py -3 <插件>/engine/rtd.py setup --project .        # 建 .rtd/，并把引擎自拷贝进去
py -3 .rtd/engine/rtd.py evidence add --kind compile_receipt --from compile.json \
  --tool "<执行器>" --command "<真实命令>"
py -3 .rtd/engine/rtd.py gate set --name compile_ok --evidence <evidence-id>
py -3 .rtd/engine/rtd.py advance --phase debug --reason "编译通过"
py -3 .rtd/engine/rtd.py status
```

门控键只有两种来源：**平台回读证据**（挂证据文件，验字段与哈希）和**当次确认原话**（`--user-confirm`）。两者不可互相顶替。

设计来源是 [plan.md](./plan.md)（脱敏版）。未脱敏原稿 `plan.raw.md` 带真实名称与替换对照表，**只在本地**，已在 `.gitignore` 里排除，别外发。

## License

MIT
