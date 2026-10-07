# 求助（Support）

先说边界：这是一个**实时数据开发流程插件**（阶段状态机 + 硬门控 + 配置化执行器），
不是数据平台本身。平台侧的问题（账号、集群、权限工单）请找对应平台的同事；
本插件的职责是"把工艺与门控做对"，不是"替你连上你的平台"。

## 该去哪

| 你遇到的是 | 去哪 |
| --- | --- |
| 装不上、装完 hook 不生效 | 先看 [README.md](README.md) 的「安装」，再开 issue（附 `python tools/adapt_hooks.py --check` 的输出） |
| 流程 / 门控行为与文档不符 | 开 issue（用「Bug 报告」模板），附最小复现：阶段、命令、完整输出、gate 键 |
| 执行器（平台 CLI / 各域 MCP）连不上 | 先跑 `rtd.py env check` 看缺口报告，再开 issue 附配置形状（**去掉口令**） |
| 想在本机起开源组件做实验 | 读 [docs/oss-lab.md](docs/oss-lab.md) 的起停配方，组件状态见 [docs/oss-component-ledger.md](docs/oss-component-ledger.md) |
| 不知道读哪份文档 | 从 [docs/README.md](docs/README.md)（文档地图）进 |
| 弄清某个概念 | [docs/glossary.md](docs/glossary.md) |
| 想贡献 | [CONTRIBUTING.md](CONTRIBUTING.md)、[GOVERNANCE.md](GOVERNANCE.md) |
| 报安全问题 | [SECURITY.md](SECURITY.md)（**不要**开公开 issue） |
| 参与讨论的底线 | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |

## 提问要带的东西

1. 你在做哪一阶段、敲的哪条命令（原文）；
2. 期望什么、实际发生什么（**完整输出**，尤其是有 gate 键的那几行）；
3. 环境（操作系统、Python 版本、插件版本、执行器形态、`mode`）；
4. 最小复现（能砍多小砍多小）。

## 支持范围

**支持**：安装与升级、阶段状态机与门控行为解释、执行器契约（`executors/contracts-*.md`）、
开源组件本地实验（`governance/oss-components.json` 的配方）、文档与模板、缺陷修复。

**不支持**（不是不礼貌，是做不到）：

- 替使用者接通其内部平台；在维护者机器上复现只有你有权访问的环境；
- 为使用者生产链路的正确性背书——本插件给的是工艺与门控，不是数据担保；
- 组件本身的运维问题（那是 Kafka / Flink / Doris 等各自的社区问题）。

## 响应预期

维护者尽力而为，不开 7×24 承诺：issue 初次回应 **7 个自然日内**；安全报告按
[SECURITY.md](SECURITY.md) 的时点。超过两周没动静，欢迎直接 ping 维护者 `@MrSuiChuan`。
