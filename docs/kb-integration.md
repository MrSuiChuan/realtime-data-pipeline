# 与知识库（记忆）插件的融合台账

实时数开插件 ↔ 知识库插件怎么接的、接成什么样、还差什么。做法对齐离线数开插件已验证的那一套。

## 一、融合的方式：共享数据契约，不共享代码

两个插件各自是独立仓库、独立 CI。融合点在**一份 JSON 契约**上，不在代码依赖上：

| | 谁 | 做什么 |
| --- | --- | --- |
| 生产端 | 知识库插件（`kbp-publish`） | 把域里的表文档同步进消费方项目的知识索引 |
| 消费端 | 本插件 | 读索引，按表名/域查口径，**只读** |

契约形状与铁律写在 `knowledge/kb-index-contract.md`；两侧各自在自己的仓库里断言同一份 schema
（本仓库 `tests/test_kb_contract.py`，生产端 `knowledge-base-plugin/tests/test_engine.py::ConsumerContractTests`），
所以**两个单仓 CI 都能钉住这条缝**，不需要同时 checkout 两个仓库。

## 二、本轮做了什么（2026-10-07）

离线插件那套融合里，消费侧有：`knowledge` 配置段、索引客户端、`uri_prefix` 铁律、跨插件契约测试。
实时插件此前只有**出站路由**（把"查/生成知识库"转给 `kbp-*` 技能），**没有任何消费侧接线**。本轮补齐：

| 补的东西 | 落点 |
| --- | --- |
| `knowledge` 配置段（`uri_prefix` + 可选 `index_path`） | `templates/config.example.json` |
| 消费侧索引客户端（`KnowledgeIndex`：search / read / status） | `engine/core.py` |
| 命令行入口 | `engine/rtd.py` 的 `knowledge status / search / read` |
| 铁律：只认受管前缀下的知识源 | `KnowledgeIndex.read` 越界直接拒 |
| 跨插件契约测试（8 条） | `tests/test_kb_contract.py` |
| 契约文档 + 出站路由补一条写回路径 | `knowledge/kb-index-contract.md`、`knowledge/routing-outbound.md` |
| 定位工作流里"消歧前先查知识库" | `workflows/runbook-discovery.md` |

## 三、索引落在哪：两个候选，按顺序探测

| 顺序 | 路径 | 谁写的 |
| --- | --- | --- |
| 1 | `<项目>/.rtd/mock/kb/index.json` | 本插件的运行目录 |
| 2 | `<项目>/.data-dev/mock/kb/index.json` | 离线数开插件的运行目录 |

**为什么是两个**：知识库插件的发布流程目前把索引**固定同步到 `.data-dev/`**，
它完全不认 `.rtd/`（实测：`rg '\.rtd' knowledge-base-plugin` 零命中）。

这里刻意**没有**去改生产端：那是一个被两个消费方共用的仓库，为了一边方便去动它，风险大于收益。
消费侧按顺序探测，**今天就能接上**；等生产端支持 `.rtd/` 时第一顺位自然生效，消费侧不用再改。

## 四、验收：真跑了一遍

```
$ .rtd/engine/rtd.py knowledge status
知识索引：<项目>/.rtd/mock/kb/index.json（存在）
  受管前缀：viking://resources/
  文档数：1
  探测顺序：<项目>/.rtd/mock/kb/index.json、<项目>/.data-dev/mock/kb/index.json

$ .rtd/engine/rtd.py knowledge search --query dwd_order_rt
查询：dwd_order_rt；命中 1 条
  - viking://resources/domains/order/tables/dwd_order_rt.md
    订单实时口径：支付成功才计入；主键 order_id 唯一。

$ .rtd/engine/rtd.py knowledge read --uri viking://resources/domains/order/tables/dwd_order_rt.md
订单实时口径：支付成功才计入；主键 order_id 唯一。

$ .rtd/engine/rtd.py knowledge read --uri file:///etc/passwd
[拒绝] 知识源不在受管前缀下：file:///etc/passwd（只认 viking://resources/ 开头的 uri）
       用 knowledge search 返回的 uri；本插件不读受管前缀之外的任何知识源
```

契约测试 8 条全过：按表名搜到、read 返回摘要、越界 uri 被拒、消费侧读的字段生产侧都在、
退到 `.data-dev` 也能读、自己那份优先、`index_path` 能覆盖、**没有索引时如实说没有（不编内容）**。

## 五、还差什么（写给之后的一轮）

| 事项 | 现状 | 触发条件 |
| --- | --- | --- |
| 生产端支持 `.rtd/` | 未做（它只写 `.data-dev/`） | 知识库插件那边排期；消费侧已留好第一顺位 |
| 真实知识库联调 | 未做 | 需要一个装了知识库插件、且发布过域知识的项目；本轮的验证用的是按契约造的索引 |
| 口径回写实时域 | 只做了**路由**（`kbp-publish`） | 需要实时域的表文档在知识库仓库里成型 |
| 引用口径的证据化 | 未做 | 目前知识只进上下文；若要"口径引用"也进证据账本，得先定 payload 形状 |

## 六、边界（别越界）

- 本插件**只读**知识索引，不写；写回是知识库插件的事（走 `kbp-publish`）；
- 知识库插件的门控与审计由它自己负责，转出后不代做；
- 铁律不放松：`uri_prefix` 之外的 uri 一律拒，哪怕调用方说"就这一次"。
