# 发布流程

发版是这个项目里**唯一不可逆的动作**（其余动作都能回退）。这份清单的目的很简单：
把"我记得要跑什么"变成"照着走就不会漏"。

## 一、版本号

* 版本只有一个来源：`.claude-plugin/plugin.json` 的 `version`；
* `.codex-plugin/plugin.json` 的版本由生成器按同一来源写出（带宿主缓存后缀），**不要手改**；
* 校验器第 5 项会拦住任何手写的版本号；
* 语义：门控语义或公开入口不兼容变更 → 升主版本；新增能力 → 升次版本；修缺陷与文档 → 升修订号。

## 二、发版前提（逐条打勾）

1. `docs/apache-readiness-audit.md` 里的 ❌ 项为空；
2. 无未处理的 `security` 标签 issue；
3. 台账里 `blocked` 的工作项都有明确原因，且原因不是"忘了做"；
4. `plan.raw.md`、`.rtd/`、`.awr/state.db*` 都在 `.gitignore` 里（校验器第 1 项会验）；
5. 脱敏词表零命中（校验器第 7 项）。

## 三、要跑的六步（与 CI 完全一致）

```bash
py -3 tools/build_codex_surface.py --check
py -3 tools/validate_plugin.py .
py -3 tools/run_evals.py --check
py -3 tools/adapt_hooks.py --check
py -3 -m pytest tests -q
```

**本地跑一遍再发**：校验器第 7、8 项在 CI 上会 SKIP（没有词表、没有本机技能包），只有本机才能真验。

### 发布前额外一步：扫历史（CI 覆盖不到）

第 7 项脱敏扫描只看当前文件树；**一条旧提交里的文档正文同样能把内部代号带出去**。
所以发布前在完整克隆里再扫一遍历史（CI 默认浅克隆，拿不到完整历史，这条只能人工做）：

```bash
git log -p main > /tmp/history.patch
grep -i -c -f tools/desensitize_terms.txt /tmp/history.patch
```

输出应为 `0`（`grep -c` 返回 0 表示没有任何一行命中）。非 0 就停下来查是哪个提交——
**在把仓库设为公开之前**处理，公开之后再撤就来不及了。

如果输出是 `grep: tools/desensitize_terms.txt: No such file`，说明本机没有词表，
这一步就没法做——去有词表的机器上跑，别跳过。

## 四、打包内容

进包的是插件的可用面：双宿主清单、`commands/` 与生成物 `skills/`、`hooks/`、`engine/`、
`governance/`、`workflows/`、`executors/`、`datasources/`、`knowledge/`、`evals/`、`tools/`、
`templates/`、`docs/`、`tests/`，以及根目录的说明与法律文件。

不进包：

| 路径 | 为什么 |
| --- | --- |
| `plan.raw.md` | 未脱敏原稿，带真实名称与替换对照表 |
| `.rtd/` | 运行时目录（状态、证据、执行记录），且含项目级配置 |
| `.awr/state.db*`、`.awr/intake/inventory.json` | 工作状态运行时，不进仓库也不进包 |
| `.tmp/` | 实验输出与临时文件 |
| `tools/desensitize_terms.txt` | 脱敏词表本身就是"要藏的名字"清单 |

打包后**验一遍**：把产物解到临时目录，搜脱敏词、搜真实平台名、确认上面那些路径都不在里面。

## 五、变更记录

`CHANGELOG.md` 按版本分节，每节至少写：新增什么、修了什么、**哪些还没做**。
"哪些还没做"不是客套——这个项目的可信度来自它敢写"未验证"。

## 六、发布动作

1. 提交版本变更（含 `CHANGELOG.md`）；
2. 打标签：`v<版本号>`；
3. 推送标签并创建 Release，附本版本的变更记录与校验方式；
4. 若分发渠道有清单（插件市场条目），同步更新版本；
5. 在 `docs/validation-report.md` 记录：谁、何时、用什么方法确认了这次发布。

## 七、发布后

* 两个宿主各装一次，确认新会话里入口能出现、hook 会弹信任提示；
* 与本版本相关的工作项走完成校验（按提交 SHA 绑定）；
* 把发布过程中新踩的坑写回本文件——下一次发布就是照着这份清单走的。
