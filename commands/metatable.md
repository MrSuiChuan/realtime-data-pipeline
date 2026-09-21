# rtd-metatable — 元表查询、创建与发布

流程见 `workflows/runbook-metatable.md`，通用骨架见 `datasources/metatable-lifecycle.md`，类型差异见 `datasources/metatable-types.md`。

## 六步

发现数据源 → 创建/编辑 → 提交 → 发布校验 → 发布 → 轮询终态。

## 五条不能改的约束

1. 先读类型文件再填字段，不凭记忆；
2. 编辑是字段级合并，但 **columns 全量替换**；项目/类型/父目录不可改；
3. `published` 参数决定查生产版还是开发版；**判断可用只认已发布版本**；
4. 物理表校验通用，建表范围看当前 schema（`governance/capability-matrix.json`）；
5. 校验通过才能发布。

## 确认是分开的

创建/编辑确认、提交确认、发布确认，**三次独立**。发布前再次回读展示定义与影响。

## 回退建表

提交报"物理表缺失"时才是回退动作：核类型范围 → 展示 DDL 模板 → 用户补全确认 → 建表 → 回读 → 重新确认提交 → 重提。**不是前置固定步骤**，范围外类型引导到平台侧。
