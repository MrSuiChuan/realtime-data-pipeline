# 真实案例复盘 → 优化台账（2026-10-10 / 10-11）

案例：在 `data-warehouse-learning` 上用本插件做一条真实的实时任务 ——
**Kafka（真订单明细）→ Flink 2.2 流式作业 → Paimon 湖表 → 商品销售额 Top3**，
八阶段全流程真跑（作业、回读、门控、证据都留档在那边仓库的 `verification/`）。

这份台账只记**这次真跑暴露出来的**东西：每条都有现场证据、有影响、有处置。
「未在本次复现」的猜测不写。

## 一、真缺口（缺能力 / 真 bug）

### O1 生命周期能力缺一个口：取消 Flink 作业

- 现场：流式作业跑完要腾出 TM 的唯一 slot 才能做批取证。试了三条路：
  `flink cancel <jobId>`（CLI）→ 抛异常；`DELETE /jobs/<jobId>` → 404；
  只有 `PATCH /jobs/<jobId>?mode=cancel` → 202。
- 影响：`rtd-lifecycle` 讲的是启停/热更新/下线，但 OSS 执行器 CLI 里**没有 stop/cancel**，
  真要用的时候只能自己写 REST 调用（本次临时脚本 `flink_rest.py`）。
- 处置：给 `oss_cli.py` 加 `flink cancel [jobId]`（PATCH 优先，失败回退 DELETE）；
  `flink jobs` 输出标出 RUNNING 的作业。

### O2 高风险动词表只有英文，中文 kind 绕过留痕门

- 现场：`rtd.py run start --kind publish` → 结束时缺 trace 被拒；
  换成 `--kind 启动` → **放行**（同一动作两种写法两种结果）。
- 影响：插件与工作流文档全用中文动词（启停/热更新/下线/回刷），中文写法就绕过了
  「高风险执行必须留追踪 ID」这条门。
- 处置：中文动词进 `HIGH_RISK_RUN_TOKENS`；hook 侧词表与它对齐（仍要求命令里出现配置的执行器名，避免误伤正文）。

## 二、易踩的环境坑（要在插件里显式拦一下）

### O3 Paimon warehouse 落在 /tmp：WSL 重启即清空

- 现场：第一轮把 warehouse 配成 `file:///tmp/rtd_paimon_top3`，`wsl --terminate` 后
  `/tmp/rtd_paimon_top3` 与 `/tmp/rtd_dwl_wh` 都不复存在（systemd-tmpfiles 清理），数据全丢。
- 影响：湖表数据看起来"跑没了"，其实是路径选址问题。
- 处置：配置/启动阶段遇到 `/tmp` 形式的 warehouse 直接告警；契约文档写明「仓库必须放持久盘」。

### O4 WSL 里的 Flink：`rest_endpoint=127.0.0.1` 连不上

- 现场：Windows 侧连 `127.0.0.1:8081` 被拒（10061），换 `wsl hostname -I` 的地址才通；
  Doris 的 9030 同样是这个规律。
- 影响：报错只有 connection refused，看不出是"WSL 转发不生效"。
- 处置：连接失败时补一句可操作提示（WSL 场景用 WSL 的 IP）+ 契约文档记这条。

### O5 单 slot 时批取证被流作业挤死

- 现场：流作业占着 TM 唯一的 slot，批查询 `Pending slot request timed out in slot pool`，
  表现像"查询挂死/校验失败"，其实是没资源。
- 影响：会误判成"湖表坏了/数据没落"。
- 处置：识别该错误并给出可操作提示（先 cancel 流作业，或把 `numberOfTaskSlots` 调大）；契约文档补一条。

## 三、体验与效率（本次真花时间的地方）

### O6 `rtd status` 只说"门控齐了"，不说下一步做什么

- 现场：八阶段里"哪个阶段要哪个门控、先置门控还是先 advance"要读源码才确定；
  本次第一版脚本就把 `discover → build` 写错（被引擎正确拒绝，但得自己找原因）。
- 处置：`rtd status` 增加 `next_action`（人类可读 + JSON），直接给"现在该做的那一条"。

### O7 缺一份"全流程"runbook

- 现场：技能文档讲的是流程意图，落地到命令（gate 属于哪个阶段、advance 的合法顺序）
  只能靠试错。
- 处置：新增 `workflows/runbook-full-flow.md`：阶段 → 门控（kind）→ 建议命令 → 常见拒绝原因，一张表看完。

## 四、看过但决定不改的

| 事项 | 结论 |
| --- | --- |
| `rtd env check` 有缺口仍返回 0 | 它是**体检**不是门：缺口逐条列在正文，拦截发生在 `advance`/`run`。保持现状，避免脚本把"报告"当失败。 |
| `evidence add` 拒绝非 JSON / 缺字段 | 本次真被它拦过一次（假回执），行为正确。 |
| `advance` 拒绝跳阶段/回跳 | 本次真被拒过两次，报错信息够用。 |

## 五、验收方式

改完必须过：`py -3 -m pytest tests -q`、`py -3 tools/validate_plugin.py .`、
`build_codex_surface.py --check`、`adapt_hooks.py --check`、`run_evals.py --check`；
新增行为的回归用例落在 `tests/`（中文高风险 kind、`flink cancel`、`status.next_action`、/tmp 告警）。
