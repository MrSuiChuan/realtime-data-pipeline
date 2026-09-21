# Contributing

## 改哪里的原则

| 你想改 | 改哪个文件 | 别改 |
| --- | --- | --- |
| 流程步骤、门禁、阶段顺序 | `commands/*.md`（唯一的流程事实源） | `skills/rtd-*/SKILL.md`（生成物） |
| 平台名、命令名、限额 | 不动仓库；写项目里的 `.rtd/config.json` | 任何仓库内文件 |
| 规则本身（什么叫"已发布"、什么算缺口） | `governance/*.md` | 工作流里复制一份 |
| 单个工作流怎么用某条规则 | `workflows/*.md` 引用 `governance/` | 在 workflow 里重述规则 |

改完 `commands/` 必须重跑生成器：

```bash
py -3 tools/build_codex_surface.py        # Windows
python3 tools/build_codex_surface.py      # macOS/Linux
```

CI 会跑 `--check`，生成物与源不一致直接失败。

## 提交前必须跑

```bash
py -3 tools/build_codex_surface.py --check
py -3 tools/validate_plugin.py .
py -3 -m pytest tests -q
```

## 两条踩过的坑（别重复）

1. **中文打印在 Windows CI 上崩**：GitHub Windows runner 的默认 stdout 编码是 cp1252，`print()` 中文直接 `UnicodeEncodeError`。所有脚本开头必须
   `sys.stdout.reconfigure(encoding="utf-8")`，重定向日志时同样。
2. **行尾**：仓库按 LF 统一（`.gitattributes`）。任何"文件哈希"类校验都必须先把行尾归一为 LF 再哈希，否则本地 CRLF 工作副本与 CI 克隆结果不一致，校验会全线飘红。

## 脱敏

`tools/desensitize_terms.txt` 里的词**不得出现在仓库任何文件中**（含 README、示例、测试夹具）。CI 会扫；想加词就往那个文件里加一行，别在别处写例外。

真实名称的落点只有一个：项目级 `.rtd/config.json`。

## 已知的校验器冲突（别急着"修好"）

`plugin-creator` 自带的校验器不认 `.codex-plugin/plugin.json` 里的 `hooks` 字段，会报 "not accepted"。但它的 spec 文档把 `hooks` 列为合法字段，且已安装的 `data-development-plugin` 在宿主 ingest 后仍保留该字段。

**本仓库保留 `hooks`**：去掉它就没有 PreToolUse 硬门。裁决依据见 `docs/validation-report.md` 末节。
