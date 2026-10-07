# 开源就绪审计（按 Apache 项目标准）

这份台账回答一个问题：**如果这个项目明天公开，它够不够格当一个正经开源项目。**

判据来源是 Apache 基金会对项目的通行要求与惯例（许可与声明、贡献流程、治理与决策、
发布流程、安全披露、社区友好度）。本项目**不是** Apache 基金会的项目，也不声称与 ASF 有关联——
借它的标准是因为那套标准经得起追问。

三个维度对应三种失败：

| 维度 | 追问 | 失败的样子 |
| --- | --- | --- |
| 流程完整性 | 外人想改一个 bug、报一个漏洞、发一个版本，知道该走哪条路吗？ | 能读能跑，但没法参与，也没法发布 |
| 合理性 | 写在文档里的承诺，机器能验吗？数字有几份？ | 文档说 A、代码做 B，改一处漏三处 |
| 友好性 | 一个陌生人 5 分钟内能不能跑出第一个结果？ | 仓库很完整，但门槛在入口处 |

状态记号：✅ 已达标｜🟡 部分达标（有缺口，已列）｜❌ 缺失（本轮补上或列为决策）

## 一、总览

| 维度 | 条目数 | ✅ | 🟡 | ❌ |
| --- | --- | --- | --- | --- |
| A 法律与许可 | 7 | 6 | 1 | 0 |
| B 流程完整性 | 9 | 9 | 0 | 0 |
| C 合理性 | 9 | 9 | 0 | 0 |
| D 友好性 | 10 | 9 | 1 | 0 |
| **合计** | **35** | **33** | **2** | **0** |

一句话结论：**这个项目的"内功"（判据机器化、诚实标注、单一事实源）本来就强于多数开源项目，
弱的是"门面与流程"**——许可声明、治理文档、发布流程、贡献入口这些外人第一眼要看的东西。
35 条里 33 条达标，还剩两条 🟡：A7（贡献者条款用 DCO 还是 CLA，待拍板）与 D9（英文版还差两份文档）。
**真正的阻塞不在这张表里**——它是历史遗留，见第八节。

## 二、A 法律与许可

| # | 条目 | 现状与证据 | 状态 |
| --- | --- | --- | --- |
| A1 | 许可证 | 原为 MIT（`LICENSE`、两份 `plugin.json` 都写 MIT）。MIT 允许闭源再分发，与"按 Apache 标准做开源"的意图不符 | ❌ → 已改为 Apache-2.0 |
| A2 | NOTICE | 原先没有。Apache-2.0 要求分发时保留声明文件 | ❌ → 已新增 `NOTICE` |
| A3 | 源文件许可头 | 原先所有源码文件都没有头（`engine/`、`hooks/`、`tools/`、`tests/`）。Apache 项目的惯例是逐文件声明 | ❌ → 已给全部自研源码加上短式头，并加机器校验 |
| A4 | 第三方依赖清单 | 原先没有。运行时不依赖第三方（纯标准库），但**实验台会下载第三方组件**——这条边界没人写清楚 | ❌ → 已新增 `docs/third-party-dependencies.md`，区分"仓库包含"与"实验台下载" |
| A5 | 商标与品牌 | 原先没有声明。项目名、插件名与 Apache 项目名（Flink/Kafka/Paimon…）的关系需要说清楚 | ❌ → 已在 `NOTICE` 与 `docs/third-party-dependencies.md` 写明"仅为兼容对象，不表示关联或背书" |
| A6 | 打包资产许可 | 仓库内不含任何第三方二进制；`skills/` 是生成物，`plan.raw.md` 已 gitignore | ✅ |
| A7 | 贡献者许可 | 原先没有贡献者条款 | 🟡 → 采用 DCO（`git commit -s`），理由与做法写在 `CONTRIBUTING.md`；是否改用 CLA 见第五节 |

## 三、B 流程完整性

| # | 条目 | 现状与证据 | 状态 |
| --- | --- | --- | --- |
| B1 | 贡献指南 | `CONTRIBUTING.md` 已有"改哪里"的对照表与两条踩坑记录，质量高于平均 | 🟡 → 本轮补上 DCO、评审流程、求助渠道 |
| B2 | 行为准则 | 原先没有 | ❌ → 已新增 `CODE_OF_CONDUCT.md`（Contributor Covenant 2.1，含执行联系方式） |
| B3 | 治理与决策 | 原先没有。谁能合并、怎么定争议、怎么改规则，全凭默契 | ❌ → 已新增 `GOVERNANCE.md`（角色、惰性共识、决策记录、争议升级） |
| B4 | 发布流程 | 原先没有。`CHANGELOG.md` 有版本小节，但没有"怎么发" | ❌ → 已新增 `docs/release-process.md`（版本规则、打包内容、校验和、发布清单） |
| B5 | 安全披露 | `SECURITY.md` 已有三层安全模型与各宿主实测强度，**诚实度罕见**；缺"支持哪些版本""多久回" | 🟡 → 已补支持版本表与响应预期 |
| B6 | Issue / PR 模板 | 原先没有，`.github/` 下只有 CI | ❌ → 已新增三个 issue 模板与 PR 模板 |
| B7 | 评审规则 | CI 有六步（生成物一致性、八项校验、evals、hook 适配、单测），但"谁在什么条件下能合"没写 | 🟡 → 写进 `GOVERNANCE.md` |
| B8 | 变更日志 | `CHANGELOG.md` 分版本、写清了每个版本"包含什么/待回填什么" | ✅ |
| B9 | 路线图与状态源 | 工作项台账在 `work-ledger.yaml`（AWR 权威源），报告按提交 SHA 归档 | ✅ |

## 四、C 合理性

| # | 条目 | 现状与证据 | 状态 |
| --- | --- | --- | --- |
| C1 | 单一事实源 | 流程只在 `commands/`、规则只在 `governance/`、组件只在 `governance/oss-components.json`；`skills/` 是生成物且有 `--check` | ✅ |
| C2 | 机器可验的承诺 | 八项静态校验 + 84 个用例 + evals 结构校验；"文档写了但没做"会被拦（本轮就拦下过两次：新组件缺契约、注册表与矩阵不一致） | ✅ |
| C3 | 诚实标注 | 已验证/未验证分开写；跑不通的组件留实测原因而不是含糊结论（`oss_components` 的 tier 与 `verified`） | ✅ |
| C4 | 可复现性 | 组件注册表里钉版本与镜像 | ✅ 已接进安装流程：注册表声明了 `sha512_url` 就下载校验和比对，取不到或不符一律失败（不静默降级）；没声明的组件不做假校验。两侧都有用例 |
| C5 | 设计文档 | `plan.md` 是脱敏设计源 | ✅ 已新增 `docs/decisions/`：6 条关键取舍，每条写背景 / 决定 / **代价** |
| C6 | 依赖策略 | 引擎与工具**只用标准库**；测试只用 pytest | ✅ |
| C7 | 版本单一来源 | 版本只在 `.claude-plugin/plugin.json`，校验器第 5 项拦手写版本号 | ✅ |
| C8 | 兼容性矩阵 | `governance/capability-matrix.json` + 组件注册表；本轮实测把 10 个组件从"未验证"推到"已通过" | ✅ |
| C9 | 已知限制 | `docs/validation-report.md`、各执行器契约的"已知缺口"、组件的 `gap` 字段 | ✅ |

## 五、D 友好性

| # | 条目 | 现状与证据 | 状态 |
| --- | --- | --- | --- |
| D1 | README 讲清是什么 | 开头两段说清"解决什么问题"（证据不实/确认失效/状态丢失），没有营销词 | ✅ |
| D2 | 五分钟上手 | 有安装与快速开始，但没有"跑完应该看到什么" | 🟡 → 本轮在 README 补了最小可验证路径（无需平台凭据即可看到第一条证据） |
| D3 | 双宿主安装 | Codex 与 Claude Code 两条路都有，含"必须开新会话"的坑 | ✅ |
| D4 | 可运行示例 | 命令示例齐全 | ✅ README 补了"跑一遍应该看到什么"：三步真实输出（含缺口报出、证据 ID、阶段与门控），不依赖任何平台 |
| D5 | 排障与 FAQ | `knowledge/faq-troubleshooting.md` + `docs/oss-lab.md` 的坑清单（很厚） | ✅ |
| D6 | 术语表 | 原先没有。门控键/证据/执行器/台账/tier 这些词对外人是黑话 | ❌ → 已新增 `docs/glossary.md` |
| D7 | 报错可行动 | 引擎与实验台的报错都是"缺口 + 下一步"两段式 | ✅ |
| D8 | 文档索引 | README 末尾有索引表；缺一个 docs 入口 | 🟡 → 已新增 `docs/README.md` 作为文档地图 |
| D9 | 多语言 | 英文是公开仓库的第一道门 | 🟡 → 已补 `README.en.md`（是什么 / 装 / 快速开始 / 执行器 / 边界 / 文档索引 / 许可）；CONTRIBUTING 与 SECURITY 的英文版仍缺 |
| D10 | 求助渠道 | 原先只能靠 issue，没写清楚"问什么去哪" | 🟡 → 已写进 README 与 CONTRIBUTING |

## 六、本轮落地的改动

| 类别 | 文件 |
| --- | --- |
| 许可与声明 | `LICENSE`（改 Apache-2.0）、`NOTICE`（新增）、全部自研源码加许可头 |
| 治理与流程 | `GOVERNANCE.md`、`CODE_OF_CONDUCT.md`、`docs/release-process.md`（均为新增） |
| 贡献入口 | `CONTRIBUTING.md`（补 DCO/评审/求助）、`.github/ISSUE_TEMPLATE/*`、`.github/PULL_REQUEST_TEMPLATE.md` |
| 安全 | `SECURITY.md`（补支持版本与响应预期） |
| 友好性 | `docs/glossary.md`、`docs/README.md`、`README.md`（许可、支持渠道、文档索引） |
| 事实澄清 | `docs/third-party-dependencies.md` |
| 机器校验 | 校验器第 1 项扩成"文件树 + 必需文件 + 许可头" |
| 组件通道 | `executors/contracts-oss-starrocks.md`、`executors/contracts-oss-pulsar.md`；`tools/lab/` 下的编排与冒烟脚本 |

顺带把一条**方法论**问题写进台账：上一轮判"GitHub 拉不动"与"GitHub 上没有二进制"都是
用 `grep` 过滤接口返回得出的——**接口被限流或报错时，过滤结果同样是空**，等于把"没查到"当成"没有"。
这一轮改用 JSON 解析并先查限流余量，结论才站得住。凡是"查不到"的结论，都要先证明查询本身没问题。

## 七、仍需项目所有者决策 / 未完成

| 项 | 为什么要你拍板 | 现在的状态 |
| --- | --- | --- |
| D7 许可证从 MIT 改成 Apache-2.0 | 这是**法律状态变更**，不是技术选择。Apache-2.0 带专利授权与更明确的声明义务，是"按 Apache 标准开源"的默认答案；若你更想保留 MIT，改回只需还原 `LICENSE` 与两份 `plugin.json` | 已按 Apache-2.0 改完并加了声明；**如果你要保留 MIT，告诉我，我一条命令还原** |
| A7 贡献者条款用 DCO 还是 CLA | DCO 门槛低（`git commit -s`），CLA 便于将来变更许可主体（比如捐给基金会） | 现用 DCO；需要 CLA 再说 |
| C4 构件校验和 | — | ✅ 已接进安装流程并有用例 |
| C5 决策记录目录 | — | ✅ 已新增 `docs/decisions/` |
| D4 端到端示例的预期输出 | — | ✅ 已补真实输出 |
| D9 英文文档 | 还差 CONTRIBUTING 与 SECURITY 的英文版（要先定术语英文对照） | 🟡 部分完成，README 已完成 |

## 八、开源前的硬阻塞：历史里的脱敏词表（2026-10-07 实测）

**结论：现在不要转公开。** 实测证据（每一步可复现）：

1. 远端 refs 只有 `refs/heads/main` → `eede9f4`，**main 的历史是干净的**
   （`git log -- tools/desensitize_terms.txt` 为空）；
2. 但用一个**空仓库** `git fetch origin 51f48bba…`（重写前的首次提交）**成功**——
   GitHub 仍按 SHA 提供被 force-push 丢掉的旧对象；
3. 该提交的树里含 `tools/desensitize_terms.txt`，blob **754 字节、内容可读**。

一旦仓库转公开，任何人拿这个 SHA 就能读到那 31 个内部代号——正好废掉这个项目
"包内零平台专有名"的核心承诺。

本地还有两条指向同一批旧提交的备份 ref（`backup-before-history-rewrite`、`original/refs/heads/main`）：
**不要推它们**，推任何一条都会把旧对象重新带上远端。

处置三选一（选好我照做）：

| 选项 | 做法 | 代价 |
| --- | --- | --- |
| (a) 让 GitHub 清掉不可达对象 | 转公开前请求 GitHub Support 清理 | 需要等，通常一两天 |
| (b) 作废词表内容 | 先判断这些代号现在还敏不敏感；不再敏感就把词表换掉，阻塞自动消失 | 要你拍板 |
| (c) 接受这些代号可被查到 | 直接公开 | 与项目自己的红线冲突，不建议 |

补充：`plan.raw.md` **从未进过仓库**（旧提交的树里也查过），这条没有风险。

### 已选定 (a)：请求 GitHub 清理不可达对象

要交给 GitHub Support 的清单（实测枚举，不是估计）：

| 项 | 值 |
| --- | --- |
| 仓库 | `MrSuiChuan/realtime-data-plugin`（私有） |
| 敏感 blob | `aac14e3471c7b499939fbc31bd5e2f160523781a`（路径 `tools/desensitize_terms.txt`） |
| 引入它的提交 | `51f48bbaad35beb0c08281ca34377a7d49388f65` |
| 重写前那条线的顶端 | `efc70c88da8db60baf04ddb7ba66326395500f98`（**26 个提交**，全部不可从当前 main 到达） |
| 当前 main | 不含该文件（`git log -- tools/desensitize_terms.txt` 为空） |

可直接投递的请求正文：

```text
Subject: Request to purge unreachable objects containing sensitive data (force-pushed history)

Repository: MrSuiChuan/realtime-data-plugin (currently private)

Hello,

I am preparing to make this repository public. During a history rewrite I removed a file that must not
be published: tools/desensitize_terms.txt (a list of internal codenames).

The file is gone from the current default branch, and the pre-rewrite commits are no longer reachable
from any branch. However, the objects are still served by SHA: from a fresh empty clone,
`git fetch origin 51f48bbaad35beb0c08281ca34377a7d49388f65` still succeeds, and the fetched tree
contains tools/desensitize_terms.txt.

Please purge the following so they are not served after the repository becomes public:

* blob            aac14e3471c7b499939fbc31bd5e2f160523781a   (path: tools/desensitize_terms.txt)
* initial commit  51f48bbaad35beb0c08281ca34377a7d49388f65   (introduced the file)
* pre-rewrite tip efc70c88da8db60baf04ddb7ba66326395500f98   (26 commits reachable from it, all
                                                              unreachable from the current main)

The current default branch (main) does not contain the file.

Please confirm once the objects have been removed, so I can verify and then make the repository public.

Thanks!
```

**清理完成后怎么验证**：再用一个空仓库跑
`git fetch origin 51f48bbaad35beb0c08281ca34377a7d49388f65`——**取不到**才算成功
（现在这条命令是会成功的，这正是阻塞所在）。

本地那两条备份 ref（`backup-before-history-rewrite`、`original/refs/heads/main`）保留与否由你定：
它们只在本地、不影响远端；删掉就没有回看旧历史的手段了，所以我没有动它们。

### 内容完整性：历史也扫过了（2026-10-07）

静态校验第 7 项只扫**当前文件树**；要保证"这个仓库可以公开"，还得扫**历史**——不然一条旧提交里的
文档正文就能把代号带出去。实测（31 个词 × main 的 44 个提交 × 约 1 MB 补丁流）：

```
结果：main 的全部历史零命中 ✓
```

扫的是 **main 可达的全部历史**；重写前那条线不在其中——它只存在于远端不可达对象里，那是本节开头那件事。
`plan.raw.md` 与词表本体从未进入 main 的历史（逐条查过）。

这条检查放进 `docs/release-process.md` 的发布清单（CI 覆盖不到：默认浅克隆拿不到完整历史，
所以它是发布前的人工步骤，不是 CI 项）。

### 2026-10-07：仓库已公开，**暴露已发生**（匿名实测）

仓库转为公开后立刻用**匿名身份**复检（这是真正的检验；之前用本机 SSH key 只能证明"所有者拿得到"）：

```
仓库 API                : 200   private = false
API contents 取旧对象    : 200   ← 匿名可读
  GET /repos/MrSuiChuan/realtime-data-plugin/contents/tools/desensitize_terms.txt?ref=51f48bba…
  返回 size=754、blob sha=aac14e3471c7、encoding=base64（与本地那份逐字节一致）
```

**结论：暴露已经发生**——任何人拿那条 URL 就能读到词表，不需要 git、不需要账号。

处置顺序（越快越好）：

1. **先把仓库改回 Private**（Settings → 最下面 Danger Zone → Change visibility）：匿名访问几秒内停止；
2. 再按前面的路处理旧对象：Support 清理，或改名保留（私有）+ 新建同名干净公开库；
3. **把这些代号当作"可能已被看到"**：它们是内部名、不是凭据，但如果保密性重要，内部该改名；
4. 确认旧对象不再被服务之后，再重新公开。

后事不忘：**公开之前就该跑匿名复检**。上一轮我用的探测带的是本机 SSH key（所有者身份），
它只能回答"所有者拿得到吗"，回答不了"陌生人拿得到吗"——这个错我犯过一次，记在这里。

#### 本地已清干净（2026-10-07，已验）

本机是除 GitHub 之外唯一还存着那份对象的地方，已彻底清掉：

```
删除 refs/heads/backup-before-history-rewrite（→ 0f88ef5）
删除 refs/original/refs/heads/main（→ efc70c8）
git reflog expire --expire=now --expire-unreachable=now --all
git gc --prune=now

剩余 ref：refs/heads/main → 87a40ea、refs/remotes/origin/main → 87a40ea
git cat-file -e aac14e3471c7… → 退出码 1（取不到）
git log --all -- tools/desensitize_terms.txt → 空
```

注意 `tools/desensitize_terms.txt`（词表本体）**仍然留在本机**——它是 gitignore 的，
静态校验第 7 项靠它工作，删了这项检查就退化成 SKIP。要清的是**进过仓库的那份**，不是本地词表。

服务端那份只能由仓库所有者处理：改回 Private（几秒止血）、请 Support 清、或删库重建。

#### 2026-10-07 已改回 Private：止血确认，但对象仍在服务端

```
匿名视角：仓库 API 404、API contents 取词表 404     ← 匿名访问已停止
所有者侧：git fetch origin 51f48bba… 成功（退出码 0） ← 那个对象仍在服务端对象库里
```

**所以"私有"只是把它藏起来，没有删掉**：现在再改回公开，暴露会立刻复现。顺序必须是
**先清对象、再公开**。

清对象的两条路（都要所有者账号，我做不了）：

1. 发 Support 工单（正文见本节上方）→ 等回执；
2. 删库 + 新建同名库（立刻，代价是 issues/PR/star）。

**验证方法有个好性质**：`git fetch` 那个旧 SHA 用**所有者身份**就能探，
而私有仓库恰好只有所有者能 fetch——所以**不用先公开就能验清理是否生效**：
取不到 = 对象已从服务端消失。等确认之后，再改公开，并补跑一次匿名复检（那才是"陌生人视角"的终检）。

期间处置：公开挂了几分钟，**把这些代号当作可能已被看到**。它们只是内部名、不是凭据；
若名声本身重要，内部改名即可，不需要更激进的措施。

## 九、怎么用这份台账

* 评审时按第四节看：**能机器验的才写进文档**；
* 发版前按 `docs/release-process.md` 的清单走一遍，本台账的 ❌ 项应当先清空；
* 有新的能力进来（新组件、新宿主），先问"它属于哪一条"，再决定要不要往台账里加行。
