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
