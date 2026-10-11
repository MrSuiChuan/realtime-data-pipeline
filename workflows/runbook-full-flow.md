# 全流程 runbook：一条实时任务从需求到上线

八阶段的落地版：每个阶段**要哪个门控**、**建议命令**、**常见拒绝原因**。
命令里的 `rtd.py` 指 `.rtd/engine/rtd.py`（`rtd setup` 会把引擎自拷到项目里）。

门控只有两类，靠 `kind` 区分：

- **回读类（readback）**：必须挂平台/湖表的真实回执 → `rtd.py evidence add` 再 `gate set --evidence <id>`；
- **确认类（confirm）**：必须挂**用户当次原话** → `gate set --user-confirm "<原话>"`，空话/代签一律拒。

| 阶段 | 本阶段门控 | 建议命令 | 常见拒绝与原因 |
| --- | --- | --- | --- |
| 1 discover | 无 | `rtd.py object set --file-id <id> --name <表> --source <来源> --version <v>`；确认源表可读（`SELECT COUNT(*)`） | — |
| 2 design | `refs_published`（回读） | `evidence add --kind refs_readback --from refs.json` → `gate set --name refs_published --evidence <id>` → `advance --phase build` | 「引用元表已发布版本回读」要求每张表 `published=true`，`null`（查不到）不算通过 |
| 3 build | `compile_ok`（回读） | 真跑一次编译/建表 → `evidence add --kind compile_receipt` → `gate set` → `advance --phase debug` | 回执 `status` 必须是终态成功；用 `--user-confirm` 代替会被拒（kind 不对） |
| 4 debug | `debug_confirmed`（确认） | 小样本真跑 + 交叉校验 → `gate set --name debug_confirmed --user-confirm "<原话>"` → `advance --phase configure` | 没有当次原话 → `gate_quote`；**不要**把历史确认拿来复用 |
| 5 configure | `sla_decided`（确认） | 参数写进作业（并行度/checkpoint/时区）→ `gate set --name sla_decided --user-confirm "<原话>"` → `advance --phase submit` | 明确跳过 SLA 也算决策，但同样要有原话 |
| 6 submit | `submit_ok`（回读） | 真提交 → 记下 jobId → `evidence add --kind submit_receipt`（`trace` 放 jobId）→ `gate set` → `advance --phase publish` | 缺 trace 会 `run_trace`；查失败不要写成"没数据" |
| 7 publish | `publish_ok`（回读） | 停流作业腾 slot → 批读结果表 → `evidence add --kind publish_receipt`（含 `object_readback`）→ `gate set` → `advance --phase start` | 发布回执必须带对象回读；只写 `status=success` 不够 |
| 8 start | `start_confirmed`（确认） | `gate set --name start_confirmed --user-confirm "<原话>"` → `rtd.py verify` 收口 | 高风险启动没有当次确认 → 拒绝 |

其它常用（不属于某个阶段门控）：

| 场景 | 命令 |
| --- | --- |
| 迁移场景的恢复点 | `gate set --name reset_time --user-confirm "<原话>" --value "<用户给的恢复点>"`（引擎不会替你取当前时间） |
| 迁移场景原任务已停 | `gate set --name source_stopped --user-confirm "<原话>"`（另附状态回读） |
| 高风险执行的追踪 ID | `rtd.py run start --kind <动作>` → `rtd.py run finish --run <id> --status 已验证 --trace <平台 jobId>` |
| 跨会话对账 | `resume --observed observed.json`（与记录不一致会拒，先处理差异） |
| 现在该做什么 | `rtd.py status`（会直接给"下一步"命令） |

## 本地开源栈的几条硬约束（2026-10-10/11 真实踩过）

1. **Paimon warehouse 不要放 `/tmp`**：WSL 重启后 systemd-tmpfiles 会清掉，湖表数据整体消失；
   放持久目录（例如 `~/oss/paimon_top3_wh`）。`oss_lab.py start` 遇到 `/tmp` 路径会告警。
2. **WSL 里的 Flink/Doris，`rest_endpoint` 要用 WSL 的 IP**（`wsl hostname -I`），
   `127.0.0.1` 在 Windows 侧转发不到。
3. **流作业占着 TM 唯一 slot 时，批取证会报 `Pending slot request timed out`**：
   先 `oss_cli.py flink cancel <jobId>`，或把 `taskmanager.numberOfTaskSlots` 调大。
4. **append 流上的聚合会被重复投递重复计入**：生产端要幂等，或聚合建在去重后的主键流上
   （本次实测：同 id 重灌一次，Top3 金额虚高约 27%）。
