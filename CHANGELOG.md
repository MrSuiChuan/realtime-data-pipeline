# Changelog

## 0.1.0 — 未发布

骨架阶段。当前仓库里已有：

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
- 八项静态校验 `tools/validate_plugin.py`（含脱敏扫描与出站路由存在性）与生成器 `tools/build_codex_surface.py`；
- 仓库规范与 CI（Windows + Linux、Python 3.11/3.12）；
- 脱敏词表 `tools/desensitize_terms.txt` 与 CI 的脱敏扫描；
- 设计源 `plan.md`（脱敏版）与本地私有 `plan.raw.md`（未脱敏 + 替换对照表）。

待回填：工具 schema 快照、九类数据源的字段契约、真实执行器联调。这些**拿不到就留空**，不用推测内容填充。

发布前不会给出可用版本号承诺。
