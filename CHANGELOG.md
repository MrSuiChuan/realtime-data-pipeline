# Changelog

## 未发布（2026-09-29）

面向**主流实时处理组件**的扩展，以及排查出来的四处真问题。版本号不升：按本仓库的惯例，
定版在 RTD-015，未定版前不给可用版本号承诺。

新增：

- **组件注册表** `governance/oss-components.json`：13 个实时组件（计算引擎 / 消息日志 / 湖表目录 /
  流存储 / 服务层 / CDC）的角色、构件、端口、内存与本地生命周期配方，按 tier 1–3 标注验证程度；
- **本地实验台** `tools/oss_lab.py`：`list / plan / status / start / stop / smoke / install`，
  **一次只起一个重型组件**（起第二个前先拦下），冒烟把"预期行数"当硬条件，原始输出落盘；
- 执行器契约三份：Kafka、Spark（Structured Streaming）、湖表格式（Iceberg / Hudi / Delta 共用一份）；
- 组件台账 `docs/oss-component-ledger.md`：每个组件现在是什么状态、还差什么；
- 配置模板 `templates/lab.example.json`（本机实验台设置，与组件知识分离）。

真跑：

- **Kafka**（单机 KRaft，消息日志层第一个跑通的开源组件）：建 topic → 灌 5 行 → 从头上读回 5 行，
  行数与灌入一致，原始输出落盘。现场与踩过的坑记在 `docs/oss-lab.md` 第十三节：
  自带守护模式的进程活不过启动它的会话、启动器立刻退出会带走刚 fork 的进程、
  进程存活判定会匹配到启动器自己的命令行、命令行工具的汇总行会被当成数据——四条都已处置。
- **Spark / Iceberg / Hudi / Delta**：已登记、构件的对齐规则写进契约，**还没真跑**，状态就是"未验证"。

### 全量真跑（同日）

注册表里能拿到构件的组件逐个起、逐个跑，判据统一是"写进去多少行、读回来多少行"：

- **通过 10 个**：Flink、Paimon、Fluss、Kafka、Spark（Structured Streaming）、Iceberg、Hudi、
  Delta、ClickHouse、Debezium（Postgres → Debezium → Kafka 的 CDC 全链路）。
  读数：Spark 流式 3 写 3 读；Iceberg / Hudi / Delta 各 5 写 5 读；ClickHouse 7 写 7 读；
  Kafka 5 写 5 读；CDC 源库 3 行 → 事件 3 条。
- **未跑通 3 个**：Pulsar（能拿到的源只有 9.6 KB/s）、Doris（版本在加速地址与归档站都是 404、
  镜像站 403）、StarRocks（分发入口 403）。原因是**构件来源**，不是配方；三项保持 tier 3 并写明实测数据。
- 实验台补了四个短板：冒烟支持工作目录与读数比对、子进程输出固定 UTF-8、安装先清目标目录、
  落点合法性护栏。现场与踩坑见 `docs/oss-lab.md` 第十四节。

### 与知识库（记忆）插件融合（2026-10-07）

对齐离线数开插件那套做法：**共享数据契约，不共享代码**。

- 新增 `knowledge` 配置段（`uri_prefix` + 可选 `index_path`）；
- 引擎新增消费侧知识索引客户端 `KnowledgeIndex`（search / read / status），
  **铁律**：`uri` 不在 `knowledge.uri_prefix` 下的一律拒绝；
- 命令行入口 `rtd.py knowledge status|search|read`；
- 跨插件契约测试 `tests/test_kb_contract.py`（8 条），与生产端
  `knowledge-base-plugin/tests/test_engine.py::ConsumerContractTests` 对着同一份 schema 断言；
- 索引按顺序探测两处：本插件 `.rtd/mock/kb/index.json` 优先，退到离线插件的
  `.data-dev/mock/kb/index.json`（生产端目前只写后者，且不认 `.rtd`）；
- 契约文档 `knowledge/kb-index-contract.md`、出站路由补 `kbp-publish` 写回路径、
  定位工作流加"消歧前先查知识库"。

台账见 `docs/kb-integration.md`（含真跑输出与还差什么）。

### 开源就绪（2026-09-30）

按 Apache 项目的通行标准自查并补齐缺口，审计台账在 `docs/apache-readiness-audit.md`。

许可与声明：

- **许可证改为 Apache-2.0**（原为 MIT），新增 `NOTICE`，全部自研源码加逐文件许可头；
- 校验器第 1 项扩成"文件树 + 必需文件 + 许可头"，新增文件漏了头会被拦。
  ⚠ 这是法律状态变更：如果你更想保留 MIT，还原 `LICENSE` 与两份 `plugin.json` 即可（见审计台账第七节）。

治理与流程（均为新增）：

- `GOVERNANCE.md`：角色、惰性共识、需要更强共识的事项、评审与合并条件、争议升级、弃用策略；
- `CODE_OF_CONDUCT.md`：Contributor Covenant 2.1，加了一条本项目特有底线（不得把"未验证"说成"已验证"）；
- `docs/release-process.md`：版本规则、发版前提、打包清单、发布动作、发布后核对；
- `CONTRIBUTING.md` 补 DCO 做法、评审规则与求助渠道；`SECURITY.md` 补支持版本与响应预期。

友好性：

- `.github/` 新增三个 issue 模板与 PR 模板（自查清单含"没改生成物""没写真实平台名"）；
- `docs/glossary.md` 术语表（每个词对应到判据）；`docs/README.md` 文档地图（按角色分入口）；
- `README.md` 补参与与支持一节、文档索引与许可说明；`docs/third-party-dependencies.md` 划清第三方与商标边界。

组件：

- **Pulsar 真跑通过**：换云厂商镜像后构件 1.7–4.2 MB/s，起单机 standalone，
  建命名空间 → 灌 9 条 → 按最早位点读回 3 条。三个坑（端口先于命名空间就绪、订阅位置参数名、
  配方里别写复合语句）写进 `executors/contracts-oss-pulsar.md`。**累计 11/13 通过**。
- **Doris 与 StarRocks 查实了分发通道**：两个项目的 GitHub Release 确实不挂二进制
  （用 JSON 解析复核过 `assets`，并先确认接口未限流），官方 CDN 对本机 403。
  换到**容器镜像**通道后 StarRocks 真跑通过（FE+BE 起得来、BE 心跳为真、写 5 读 5）；
  Doris 复用同一份编排脚本，FE 镜像已就位，BE 镜像仍在拉取。
  **累计 12/13 通过**，未跑通的原因从"找不到构件"变成"镜像体积与拉取时间"。
- 更正上一轮两处错误结论：说"GitHub 拉不动"（复测同一地址 744 KB/s）与
  "GitHub 上没有二进制"（当时是用 `grep` 过滤接口返回，没排除限流）。
  **一次测速采样、一次 grep 过滤，都不能当结论。**

修复（都是实测发现，不是推测）：

- 开源执行器清单原先有**三份副本**（引擎里手写、契约文档、能力矩阵），加组件要改四处且无人校验 →
  引擎改为从注册表读 tier 1/2 组件，校验器第 3 项扩成"矩阵引用 + 注册表一致性"，三份绑成一份；
- 开源路径的"配全"判定用 `all(...)`：注册表一扩，就把"只配 Flink + Fluss"的人误报成没配齐 →
  改为按**已开始的子集**判定（动过的必须配全，没动过的不算缺口）；
- 注册表读不出来时原会静默退化成"没有开源执行器"，把配置错误伪装成"没配" → 现在进缺口并显式报出；
- tier 3 组件（Pulsar / Debezium / Doris / StarRocks / ClickHouse）只登记角色与配置形状，
  校验器会拦"tier 3 却带了本地启动配方"这种自相矛盾的写法。

## 0.1.0 — 首个公开版本（2026-09-23）

首个公开版本。刻意不叫 1.0：平台路径（平台 CLI / 各域 MCP）未经真实环境验证，按"未验证"呈现；开源路径（Flink / Paimon / Fluss）已在本机实测跑通。

包含：

- 双宿主清单（`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`）；
- 规制层 7 件：安全宪法、执行器仲裁、身份与时间、输出契约、反例库、执行器接入、能力矩阵；
- 工作流层 11 份：定位 / 研发 / 迁移 / 元表 / 启停 / 巡检 / 诊断 / 调参 / 环境 / 版本生效矩阵 / 衔接总图；
- 12 个命令入口与从它们生成的 Codex 技能（`rtd-*`）；
- 执行器契约 5 份（CLI / 运维 / 研发 / 资产 / 引擎只读）+ schema 目录占位；
- 数据源层：元表生命周期（含 5 条关键约束）与九类类型槽位；
- 知识层 3 件（FAQ 排查、出站路由、链接解析）；
- 引擎 `engine/rtd.py`：阶段状态机、门控键、证据账本、执行记录、跨会话对账、运行时自检；
- hooks：PreToolUse 三条硬门（证据保护 / `--yes` 自行追加 / 高风险动词）+ SessionStart 阶段提醒；
- evals 五组（router / dev / ops / safety / contract）；
- 巡检评分脚本 `tools/score_inspection.py`：吃快照出报告（只出报告、不碰网络、不覆盖历史目录），覆盖不足时给"已观测风险暂评分"并夹住上限；
- 证据绑定对象身份（文件级 ID + 版本），换对象或换版本旧证据一律作废；
- 非顺序阶段推进（回跳/跳阶段）必须写理由；运行时记录插件版本；
- 八项静态校验 `tools/validate_plugin.py`（含脱敏扫描与出站路由存在性）与生成器 `tools/build_codex_surface.py`；
- 开源栈薄封装 CLI `tools/oss_cli.py`：一个入口管 Flink 与 Fluss（作业查询走 REST、SQL 走客户端/网关两条通道），
  `evidence refs` 产出 `refs_readback` JSON，查失败记 `published: null` + 原因而不是"未发布"；
- 仓库规范与 CI（Windows + Linux、Python 3.11/3.12）；
- 脱敏词表 `tools/desensitize_terms.txt` 与 CI 的脱敏扫描；
- 设计源 `plan.md`（脱敏版）与本地私有 `plan.raw.md`（未脱敏 + 替换对照表）。

待回填：工具 schema 快照、九类数据源的字段契约、真实执行器联调。这些**拿不到就留空**，不用推测内容填充。

发布前不会给出可用版本号承诺。
