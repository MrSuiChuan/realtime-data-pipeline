# 验收报告目录

这里放 AWR 完成流程用的 version 1 验收报告。命名：

```
<工作项小写>-completion-<提交短SHA>.json
例：rtd-016-completion-00f1f3b.json
```

## 三个约定（都是实测踩出来的）

1. **报告全量保留**。它按提交 SHA 绑定证据，删掉会让那一次验证无法复核。单份约 2 KB，几十份也不到 100 KB，没有压缩的必要。
2. **完成校验按提交计**。`awr intake inspect` 不带 `--source-sha` 时只看到"状态声明"，看不到"验证结论"；核对某次提交必须显式带上：

   ```bash
   awr intake inspect --project . --source-sha <提交> --json
   ```

3. **锚点约定**：验证锚定在**代码提交**上；紧随其后的"只写台账/报告"的提交不重新锚定（否则每推一次就要重绑一轮）。看某个提交的验证情况时，用它前一个代码提交的 SHA。

## 快速看最新一轮

```bash
py -3 tools/awr_reports.py            # 每个工作项最新一轮是哪个提交
py -3 tools/awr_reports.py --limit 2  # 只看最近两轮
```

## 一次历史重写的后果（2026-09-23）

开源前做过一次历史重写：把脱敏词表从所有提交里摘掉（词表里是真实内部代号，不能随仓库公开）。代价是**重写之前的提交哈希全部变了**：

- 本目录 48 份报告里，**47 份绑定的提交已不在 `main` 的历史中**（`git log <sha>` 查不到，GitHub 上点进去会 404）；
- 仍指向现有提交的只有重写之后生成的那一份（`rtd-014-completion-f1f4054.json`）。

所以这些报告是**当时的验证记录**，不是可点击回跳的引用。要复核"现在这个版本到底过不过"，用仓库里可复现的检查，而不是翻旧报告：

```bash
py -3 tools/validate_plugin.py .        # 八项静态校验（本地有词表时第 7 项是真扫）
py -3 -m pytest tests -q                # 49 个用例
py -3 tools/run_evals.py --check        # evals 结构
py -3 tools/build_codex_surface.py --check
```

新的验收报告按当前提交哈希命名，绑定关系从这份 README 之后重新累积。
