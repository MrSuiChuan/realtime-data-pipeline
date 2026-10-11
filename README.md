# realtime-data-plugin

把实时数据任务的研发工艺翻成**状态机 + 硬门控**。AI 在门内自己干活，阶段出口只认机器证据。

[![ci](https://github.com/MrSuiChuan/realtime-data-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/MrSuiChuan/realtime-data-pipeline/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)

装进 Codex 或 Claude Code，它调用你本地的 Flink、Kafka、湖表与元数据平台，把一条实时任务从需求推到上线，
每一步都留机器可核验的证据。它不替你决定口径，也不替你动线上状态，它负责的是让这两件事都留痕、可复核。

## 目录

- [它解决什么问题](#它解决什么问题)
- [什么任务适合用它](#什么任务适合用它)
- [运行流程](#运行流程)
- [快速开始](#快速开始)
- [引擎 CLI 速查](#引擎-cli-速查)
- [执行器：两条路](#执行器两条路)
- [开源栈：13 个组件与两个工具](#开源栈13-个组件与两个工具)
- [与记忆（知识库）插件的融合](#与记忆知识库插件的融合)
- [真实案例](#真实案例)
- [要求](#要求)
- [范围与边界](#范围与边界)
- [文档索引](#文档索引)
- [本地自检](#本地自检)
- [现在到哪一步](#现在到哪一步)
- [参与与支持](#参与与支持)
- [License](#license)

## 它解决什么问题

实时任务开发的坑不在写不写得来 SQL，而在三件事上。

1. **证据不实**。编译看起来过了、发布应该成功了、调试没报错，然后线上发现表没数据；
2. **确认失效**。一次同意被当成一路放行，启动、回刷、下线这些改线上状态的动作没有当次确认；
3. **状态丢失**。换个会话接着干，对象 ID、版本、追踪 ID 全凭记忆，重发一次写操作就是事故。

插件把这三件事变成机制，阶段出口有门控键，门控键只能由引擎按证据写入，证据落盘可核验，续跑先回读平台真实状态。

## 什么任务适合用它

| 场景 | 它替你盯住的事 |
| --- | --- |
| **从零做一条实时任务**（消息 → 计算 → 湖 / 仓） | 口径写成可检验的断言、引用表可回读、编译终态成功、结果与独立基准对得上 |
| **老任务迁移到新引擎或新平台** | 原任务是否真停、恢复点由用户给定（拒绝自动取当前时间）、迁移前后读回一致 |
| **线上巡检与异常诊断** | 只看只读接口，巡检过程不允许顺手改状态，要改就走另一条带确认的路 |
| **调参与启停**（热更新、下线、回刷、取消） | 高风险动作要当次确认原话，执行结束要留平台追踪 ID，拿不到就如实记失败 |
| **跨会话、跨人交接** | 证据账本 + 执行记录 + 跨会话对账，状态与平台回读不一致先停下处理差异 |
| **本地没平台、只有开源组件** | 开源路径：13 个组件注册表 + 本地实验台，起停、探活、冒烟都有配方，真跑过再记账 |

不适合的情况也说清。它不是调度平台，不排班、不报警；它不替你设计业务口径，口径得你自己拍板；
没配执行器时它只到门控这一步就停，不会自己猜命令名、也不会自动装组件。

## 运行流程

八个阶段，一个方向走到底。

```text
discover → design → build → debug → configure → submit → publish → start
发现       设计     构建    调试    配置        提交      发布      启动
```

每个阶段有自己的门控，门控只有两类来源，**不允许互相顶替**。

| 阶段 | 门控键 | 类型 | 靠什么过 |
| --- | --- | --- | --- |
| design | `refs_published` | 回读 | 引用元表的已发布版本回读，每张表都要 `published=true` |
| build | `compile_ok` | 回读 | 编译终态回执（`compile_receipt`），中途成功不算 |
| debug | `debug_confirmed` | 当次确认 | 调试模式选择与用户的当次原话 |
| configure | `sla_decided` | 当次确认 | SLA 决策，明确跳过也算决策，但同样要原话 |
| submit | `submit_ok` | 回读 | 提交终态回执（`submit_receipt`） |
| publish | `publish_ok` | 回读 | 发布终态回执 + 对象回读（`publish_receipt` 必须带 `object_readback`） |
| start | `start_confirmed` | 当次确认 | 启动这类高风险动作的当次确认 |
| start（迁移） | `source_stopped` / `reset_time` | 当次确认 | 原任务已停的声明另附状态回读；恢复点必须由用户给具体值 |

几条不放松的纪律。回读类门控挂不上平台证据、想用一句我觉得行替代，拒；
确认类门控没写当次原话、想复用历史确认，拒；跨阶段跳、回跳不带理由、空理由，拒；
高风险执行结束时没留追踪 ID，拒。

证据是四类结构化回执，落盘带哈希，可以在账本里逐条复核。

| 证据类型 | 必填字段（节选） | 用途 |
| --- | --- | --- |
| `refs_readback` | `tables[].published`、`observed_at` | 引用表已发布 |
| `compile_receipt` | `status`、`observed_at` | 编译终态 |
| `submit_receipt` | `status`、`observed_at` | 提交终态 |
| `publish_receipt` | `status`、`observed_at`、`object_readback` | 发布终态 + 对象回读 |

查询失败不许写成没有数据，这是硬规则。查不到是 `published: null` 加原因，空是空，编是编，两回事。

## 快速开始

两个宿主共用同一套引擎、工作流与 hook 脚本，装哪个都行，也可以都装。

```bash
# Codex
codex plugin marketplace add <本仓库路径>
codex plugin add realtime-data-plugin@personal

# Claude Code（仓库自带 .claude-plugin/marketplace.json）
claude plugin marketplace add <本仓库路径>
claude plugin install realtime-data-plugin@realtime-data-plugin
```

**装完必须开新会话**，插件列表在会话启动时加载。首次加载时宿主会问是否信任这个插件的 hook，
**要信任**，否则硬门不生效，原因与核实方法见 `docs/host-hooks.md`。

```bash
# 1) 在项目里初始化运行时，然后按提示填执行器配置
/rtd-setup                     # Claude Code 斜杠命令；Codex 侧入口是技能 rtd-setup

# 2) 开工，从需求到上线，阶段出口有门控
/rtd-dev "把这两张实时表做成一条宽表任务，10 秒聚合"
```

初始化会创建 `<项目>/.rtd/`（状态、证据、执行记录）并生成 `config.json` 模板，权限 0600。
填好执行器后，`rtd-status` 会列出还缺哪一项，`rtd-setup` 的收尾输出也会直接给缺口原因。

## 引擎 CLI 速查

引擎是 `.rtd/engine/rtd.py`，`setup` 时自拷贝到项目里，之后跟着项目走，不受插件升级影响。

| 命令 | 做什么 |
| --- | --- |
| `setup` | 建运行时、自拷贝引擎、生成配置模板、把 `.rtd/` 追加进项目 `.gitignore` |
| `status` | 当前阶段 + 本阶段门控缺口 + 下一步该跑哪条命令 |
| `object set` | 登记当前对象，文件级 ID、名称、版本、实例 |
| `evidence add` | 登记并当场校验结构化回执，返回证据 ID |
| `gate set` | 置门控键，`--evidence <id>` 或 `--user-confirm "<原话>"` 二选一 |
| `advance` | 阶段推进，回跳与跳阶段要 `--allow-back --reason` |
| `run start` / `run finish` | 执行记录，高风险动作结束时必须带 `--trace` |
| `env check` | 执行器体检，两条路各缺什么逐项列出 |
| `knowledge status` / `search` / `read` | 读记忆（知识库）插件写下的知识索引，只读 |
| `resume` | 跨会话对账，状态与平台回读不一致就停 |
| `verify` | 收口自检，状态、证据哈希、门控引用一致性 |

每个阶段该配哪个门控、常见拒绝长什么样，写在 `workflows/runbook-full-flow.md`，一张表看完。

## 执行器：两条路

真实命令名、MCP 服务名、地址与限额**全部来自项目级 `.rtd/config.json`**，仓库内不含任何平台专有名。
配置缺项时的行为是报缺口并停，不猜命令名、不自动安装、不自动切到另一条路。

| 路径 | 组成 | 判定方式 |
| --- | --- | --- |
| 平台路径 | 平台 CLI（`executors.cli`）与各域 MCP（`mcp_dev` / `mcp_ops` / `mcp_asset` / `mcp_engine`） | 至少配一个入口，`rtd.py env check` 逐项体检 |
| 开源路径 | `governance/oss-components.json` 里 tier 1/2 组件的 `required_keys` | 按**已开始的子集**判定，动过的组件必须配全，没动过的不算缺口 |

两条路各自判定，不会拿另一条路的要求来报缺口。平台路径的真实环境验证**尚未完成**，按未验证呈现。

## 开源栈：13 个组件与两个工具

注册表登记 13 个实时组件，覆盖计算引擎、消息日志、湖表目录、流存储、服务层、变更捕获六类角色，
每个都标注构件来源、本地生命周期配方与验证程度。**当前 13 个全部在本机真跑过**，
逐个组件的现状、缺口与原始输出在 `docs/oss-component-ledger.md`。

`tools/oss_cli.py` 是 Flink 与 Fluss 的薄封装，只依赖标准库，配置读 `.rtd/config.json` 的 `executors.oss_*`。

```bash
py -3 tools/oss_cli.py flink jobs                    # 列作业，RUNNING 的会标出来占着 slot
py -3 tools/oss_cli.py flink status <jobId>          # 单作业状态
py -3 tools/oss_cli.py flink cancel [jobId]          # 取消作业，不填就取消当前在跑的那个
py -3 tools/oss_cli.py flink submit -f job.sql       # 提交 DDL / DML
py -3 tools/oss_cli.py fluss  sql -f fluss.sql       # Fluss 走 Flink 的 catalog
py -3 tools/oss_cli.py evidence refs --table paimon.db_lab.t_orders --raw-dir raw/
```

`tools/oss_lab.py` 管本机实验台，装构件、起停组件、探就绪、跑冒烟，组件知识同样来自注册表。

```bash
py -3 tools/oss_lab.py list                       # 登记了哪些组件、哪些构件还没配
py -3 tools/oss_lab.py plan oss_kafka             # 只看起停配方与冒烟步骤，不执行
py -3 tools/oss_lab.py start oss_kafka            # 起，有别的重型组件在跑会被拦
py -3 tools/oss_lab.py smoke oss_kafka --count 3  # 建 topic → 灌 3 行 → 读回 3 行，原始输出落盘
py -3 tools/oss_lab.py stop  oss_kafka            # 停掉再上下一个
```

几条从实测里来的纪律直接写进工具，不是写在文档里。一次只起一个重型组件；冒烟把预期行数当硬条件，读回 0 行不算通过；
配置里落在临时目录的路径会先告警（重启即丢，我们真丢过一次数据）；撞上槽位不够会提示先取消哪个作业。

## 与记忆（知识库）插件的融合

实时任务的口径与表语义常常已经写在知识库里。插件用**一份 JSON 契约**接上它，不依赖代码，也不共享仓库。

| 谁 | 做什么 |
| --- | --- |
| 生产端（知识库插件） | 发布时把域里的表文档同步进消费方项目的知识索引 |
| 消费端（本插件） | 读索引，按表名或域查口径，**只读**，`uri` 不在受管前缀下一律拒 |

两个仓库各自对着同一份 schema 断言，所以单仓 CI 也能钉住这条缝，不需要同时 checkout 两个仓库。
契约形状、探测顺序与真实联调记录见 `docs/kb-integration.md` 与 `knowledge/kb-index-contract.md`。

## 真实案例

这套东西不是纸面设计，拿它真跑过一条完整链路，Kafka 灌真实订单明细，Flink 流式作业写 Paimon 的
ODS / DWD / ADS 三层，最后产出「实时场景商品销售额 Top3」，并用源库独立算一遍做交叉校验，三行结果逐项一致。

过程中被它拦下的真问题写在 `docs/optimization-real-case-2026-10.md`，比如同一批消息重复投递会让直接建在
消息流上的聚合把金额算高约百分之二十七，而行数看起来完全正常。

跑这条链路的完整现场和读数在 `docs/validation-report.md`，按真实案例复盘出来的七处优化在
`docs/optimization-real-case-2026-10.md`。

## 要求

- Python 3.11+，引擎、校验器与工具只用标准库，跑测试需要 pytest；
- Windows / macOS / Linux 均可，hook 的启动器用 `tools/adapt_hooks.py` 按平台适配；
- 不需要任何平台凭据就能启动，配置为空时引擎报缺口并停下，不替你猜。

## 范围与边界

| 做 | 不做 |
| --- | --- |
| 阶段状态机与门控键，证据与当次确认两类，不可互替 | 不内置任何平台的命令名与服务名，走项目级配置 |
| 证据账本（哈希可验）、执行记录、跨会话对账 | 不替你做线上变更，写操作都要当次确认 |
| 十份 runbook 与十六份执行器契约 | 不打包平台专有的 schema 快照与内部测试集 |
| 开源栈 13 个组件已本地真跑，组件台账逐个回填 | 平台路径（平台 CLI 与各域 MCP）未经真实环境验证，按未验证呈现 |
| 与知识库插件的只读知识索引契约，两侧各自有 CI 断言 | 不写知识索引，写回是知识库插件的事 |

## 文档索引

完整地图见 `docs/README.md`，按「我是谁」分，第一次来、想用起来、要参与开发、要发版、要看设计。

| 文档 | 内容 |
| --- | --- |
| `plan.md` | 设计源（脱敏版），融合判断、关键合并与构建顺序 |
| `workflows/runbook-full-flow.md` | 全流程 runbook，阶段到门控到命令到常见拒绝 |
| `docs/README.md` | 文档地图，不同角色从哪开始看 |
| `docs/glossary.md` | 术语表，门控键、证据、执行器、台账、tier 这些词到底指什么 |
| `docs/host-hooks.md` | 两个宿主里 hook 的实测记录，什么生效、什么不生效、怎么核实 |
| `docs/oss-lab.md` | 本地开源栈实验，安装、跑通过程与踩过的坑 |
| `docs/oss-component-ledger.md` | 组件台账，13 个组件的角色、构件就绪判定、真跑到哪一步 |
| `docs/kb-integration.md` | 与记忆（知识库）插件的融合台账，含真跑输出与还差什么 |
| `docs/optimization-real-case-2026-10.md` | 真实案例复盘出来的优化台账 |
| `docs/validation-report.md` | 验证记录，哪些已验证、哪些没有、边界在哪 |
| `docs/apache-readiness-audit.md` | 开源就绪审计，按 Apache 标准逐条自查，含未完成项 |
| `docs/release-process.md` | 发布流程与打包清单 |
| `docs/third-party-dependencies.md` | 第三方边界，仓库里有什么、实验台会下载什么、商标怎么用 |
| `governance/` `workflows/` `executors/` `datasources/` | 规制层、工作流层、执行器契约、数据源契约 |

## 本地自检

```bash
py -3 -m pytest tests -q                     # 全量用例
py -3 tools/validate_plugin.py .             # 八项静态校验，含脱敏扫描
py -3 tools/build_codex_surface.py --check   # 生成物与命令源一致
py -3 tools/adapt_hooks.py --check           # hook 启动器与平台一致
py -3 tools/run_evals.py --check             # 评测集结构
py -3 tools/awr_reports.py                   # 台账验收报告，每个工作项最新一轮是哪个提交
```

## 现在到哪一步

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Q0–Q2 | 设计源、仓库骨架与双宿主清单、CI、规制层 7 件 | 完成 |
| Q3 | 工作流层，13 个命令入口与十份 runbook | 完成 |
| Q4–Q6 | 执行器契约 16 份与配置层、数据源层、知识层与出站路由 | 完成 |
| Q7 | 引擎与 hook 硬门控 | 完成 |
| Q8 | 评测集五组与八项静态校验 | 完成，真实平台联调仍待做 |
| Q9 | 巡检评分脚本，离线出报告 | 完成，阈值待真实窗口校准 |
| Q10 | 开源栈 13 个组件逐个真跑与组件台账 | 完成 |
| Q11 | 真实案例全流程与复盘优化 | 完成，见 `docs/optimization-real-case-2026-10.md` |
| Q12 | 记忆（知识库）插件融合 | 完成，见 `docs/kb-integration.md` |

## 参与与支持

| 你想 | 去哪 |
| --- | --- |
| 提缺陷 / 提能力 | `.github/ISSUE_TEMPLATE/` 里挑一个模板 |
| 配置接不上 | 用配置求助模板，附 `rtd.py env check` 的输出 |
| 贡献代码 | `CONTRIBUTING.md`，含 DCO 与评审流程 |
| 了解谁说了算 | `GOVERNANCE.md` |
| 报安全问题 | `SECURITY.md`，**不要开公开 issue** |
| 参与讨论的底线 | `CODE_OF_CONDUCT.md` |

## License

Apache License 2.0，见 `LICENSE` 与 `NOTICE`。

第三方名称与商标的边界写在 `docs/third-party-dependencies.md`。本仓库不包含任何第三方二进制，
文档里提到的组件名只用于说明兼容对象与实测事实，不表示赞助、背书或关联。

设计来源是 [plan.md](./plan.md)（脱敏版）。未脱敏原稿 `plan.raw.md` 带真实名称与替换对照表，
**只在本地**，已在 `.gitignore` 里排除，别外发。
