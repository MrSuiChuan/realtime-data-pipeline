# 跨插件契约：知识库（记忆）索引

实时数开插件与知识库插件怎么接上。做法对齐离线数开插件已验证的那一套——**不共享代码，共享一份数据契约**，
两侧各自在自己的仓库里断言同一份 schema。

## 索引形状

```json
{
  "documents": [
    {
      "uri": "viking://resources/domains/<域>/tables/<表>.md",
      "domain": "<域>",
      "layer": "<表名首段>",
      "tables": ["<表>"],
      "abstract": "一句话口径"
    }
  ]
}
```

消费侧真正读的字段是 `uri` / `domain` / `layer` / `tables` / `abstract`
（登记在 `engine/core.py` 的 `KB_DOCUMENT_FIELDS`）。

## 索引落在哪（两个候选，按顺序探测）

| 顺序 | 路径 | 谁写的 |
| --- | --- | --- |
| 1 | `<项目>/.rtd/mock/kb/index.json` | 本插件的运行目录 |
| 2 | `<项目>/.data-dev/mock/kb/index.json` | 离线数开插件的运行目录 |

**为什么是两个**：知识库插件的发布流程目前把索引固定同步到 `.data-dev/`（它还不认 `.rtd/`）。
与其去改那个共享的生产端，消费侧先按上面的顺序探测——**今天就能接上**，等生产端支持 `.rtd/` 时，
第一顺位自然生效，不需要再动消费侧。

`knowledge.index_path` 可以显式覆盖，用于索引放在别处的情况。

## 铁律：只认受管前缀下的知识源

`uri` 必须以 `knowledge.uri_prefix`（默认 `viking://resources/`）开头，否则 `read` 直接拒绝：

```
$ .rtd/engine/rtd.py knowledge read --uri file:///etc/passwd
[拒绝] 知识源不在受管前缀下：file:///etc/passwd（只认 viking://resources/ 开头的 uri）
       用 knowledge search 返回的 uri；本插件不读受管前缀之外的任何知识源
```

为什么要有这条：索引是**别的插件写进来**的。不加限制，`read` 就成了"给什么 uri 就读什么"的接口，
等于把知识来源交给写入方任意决定。前缀是这条缝上的唯一约束，不能松。

## 契约在哪被断言

| 侧 | 断言位置 |
| --- | --- |
| 消费端（本仓库） | `tests/test_kb_contract.py` |
| 生产端 | `knowledge-base-plugin` 的 `tests/test_engine.py::ConsumerContractTests` |

两侧各自断言同一份 schema，**两个单仓 CI 都能钉住这条缝**，不需要同时 checkout 两个仓库。
改契约（字段名、前缀语义）必须两边一起改。

## 怎么用

```bash
py -3 .rtd/engine/rtd.py knowledge status                    # 索引在哪、几条、前缀是什么
py -3 .rtd/engine/rtd.py knowledge search --query <表名或域>  # 查口径
py -3 .rtd/engine/rtd.py knowledge read   --uri <search 给的 uri>
```

没有索引时如实说"不存在 / 0 条"，`search` 返回空、`read` 返回空串——**不编内容**。
