# 文档地图

从哪开始看，取决于你是谁。

## 我是第一次来

1. 仓库根目录的 `README.md`——它解决什么问题、怎么装、五分钟跑出第一条证据；
2. `docs/glossary.md`——术语表。先扫一眼，后面少猜很多词；
3. `docs/oss-component-ledger.md`——它现在支持哪些实时组件、各自验到什么程度。

## 我想用起来

| 我想要 | 看这里 |
| --- | --- |
| 装插件、初始化一个项目 | `README.md` 的"安装"与"快速开始" |
| 按流程做一条任务 | `workflows/` 下的 runbook，入口是 `workflows/workflow-map.md` |
| 接开源栈（Flink / Kafka / Spark / 湖表 / ClickHouse / CDC） | `executors/contracts-oss-*.md` 与 `governance/oss-components.json` |
| 在本机起真实组件做实验 | `docs/oss-lab.md`（谁跑过什么、踩过什么坑） |
| 出问题了 | `knowledge/faq-troubleshooting.md` |

## 我要参与开发

| 我想要 | 看这里 |
| --- | --- |
| 提第一个 PR | `CONTRIBUTING.md`（改哪里的原则、提交前必须跑什么） |
| 知道谁说了算、怎么定争议 | `GOVERNANCE.md` |
| 参与讨论的底线 | `CODE_OF_CONDUCT.md` |
| 报安全问题 | `SECURITY.md` |

## 我要发版或做开源合规

| 我想要 | 看这里 |
| --- | --- |
| 发一个版本 | `docs/release-process.md` |
| 按 Apache 标准自查 | `docs/apache-readiness-audit.md`（三个维度逐条，含未完成项） |
| 查第三方与商标边界 | `NOTICE` 与 `docs/third-party-dependencies.md` |
| 看哪些验过、哪些没有 | `docs/validation-report.md` 与 `docs/oss-component-ledger.md` |

## 我要看设计与实现

| 我想要 | 看这里 |
| --- | --- |
| 整体设计（脱敏版） | `plan.md` |
| 引擎与门控的实现 | `engine/core.py`（文件头的职责与诚实边界） |
| 工作状态从哪来 | `work-ledger.yaml` 与 `docs/awr-intake.md` |
| 宿主 hook 实测到什么程度 | `docs/host-hooks.md` |

## 约定

* 仓库里的**规则只写一份**：结论在 `governance/`，流程在 `commands/`，组件认知在
  `governance/oss-components.json`；别处只引用、不复述；
* `skills/` 是生成物（由 `commands/` 生成），不要直接改；
* 写到文档里的数字与承诺，要么有机器校验，要么标注"未验证"。
