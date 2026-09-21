# rtd-migrate — 实时 SQL 任务迁移

流程见 `workflows/runbook-migration.md`。默认**停在编译通过**。

## 步骤

1. 定位源任务并预览（长内容分级读取，用总行数校验完整性）；
2. 一次性确认三项参数：目标项目（默认同项目）、新名称（默认原名 + `_migrated`）、目录（用目录搜索，不用名称搜索反查）；
3. 一条命令完成迁移到编译（执行器负责分片与写入，Skill 不自己拼内容）；失败用返回的阶段与目标 ID 续查，不另起第二个目标；
4. 要提交/发布/启动，另外问。

## 启动门（最严）

```
py -3 .rtd/engine/rtd.py gate set --name source_stopped --user-confirm "<用户原话>"
py -3 .rtd/engine/rtd.py gate set --name reset_time --user-confirm "<用户原话>" --value "<用户给的时间>"
py -3 .rtd/engine/rtd.py gate set --name start_confirmed --user-confirm "<用户原话>"
```

三条缺一即停：源任务未确认停止 → 最多迁到编译成功；恢复点必须用户给，引擎会拒绝"看起来就是当前时间"的值。

跨会话重新启动时**重新确认**，不沿用上一会话的记忆。
