#!/usr/bin/env python3
# Copyright 2026 AI实战技能圈
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""八项静态校验（plan.md 第十章的落地实现）。

    py -3 tools/validate_plugin.py .        # Windows
    python3 tools/validate_plugin.py .      # macOS/Linux

退出码：0 = 全过；1 = 有校验失败。
第 7 项（脱敏）是硬红线：命中即失败，不给白名单例外。
"""

from __future__ import annotations

import json
import os
import re
import sys
from glob import glob
from pathlib import Path

def _configure_stdio() -> None:
    """把 stdout/stderr 设成 UTF-8。

    捕获流（pytest、某些宿主）没有 reconfigure —— 直接调用会让整个模块导入失败，
    所以这里一律带兜底：宁可输出编码不完美，也不能让模块导入崩掉（CI 上踩过）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue


_configure_stdio()


# 默认根目录用脚本自身位置推导，**不要**用 sys.argv——
# 这个模块会被测试导入，而调用方（pytest）的 argv 里是测试文件路径，
# 拿它当根目录会把 ROOT 指到测试文件上（踩过：整项校验静默失效）。
DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".tmp", ".rtd", "logs", "node_modules"}
# plan.raw.md 是未脱敏原稿，本地私有（.gitignore 已排除），不参与扫描。
SKIP_FILES = {"desensitize_terms.txt", "plan.raw.md"}
TERMS_FILE = ROOT / "tools" / "desensitize_terms.txt"

# 第 1 项：结构必须齐的路径（随各阶段落地逐步加长）
REQUIRED_PATHS = [
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "plan.md",
    "engine/core.py",
    "engine/rtd.py",
    "hooks/common.py",
    "hooks/gates.py",
    "hooks/pretooluse.py",
    "hooks/sessionstart.py",
    "hooks/hooks.json",
    "hooks/codex-hooks.json",
    "governance/safety-constitution.md",
    "governance/executor-arbitration.md",
    "governance/identity-and-time.md",
    "governance/response-contracts.md",
    "governance/anti-patterns.md",
    "governance/mcp-setup.md",
    "governance/capability-matrix.json",
    "governance/oss-components.json",
    "workflows/runbook-discovery.md",
    "workflows/runbook-dev.md",
    "workflows/runbook-migration.md",
    "workflows/runbook-metatable.md",
    "workflows/runbook-lifecycle.md",
    "workflows/runbook-inspection.md",
    "workflows/runbook-diagnosis.md",
    "workflows/runbook-tuning.md",
    "workflows/runbook-environment.md",
    "workflows/version-effect-matrix.md",
    "workflows/workflow-map.md",
    "executors/contracts-cli.md",
    "executors/contracts-ops-mcp.md",
    "executors/contracts-dev-mcp.md",
    "executors/contracts-asset-mcp.md",
    "executors/contracts-engine-mcp.md",
    "executors/contracts-oss-flink.md",
    "executors/contracts-oss-paimon.md",
    "executors/contracts-oss-fluss.md",
    "executors/contracts-oss-kafka.md",
    "executors/contracts-oss-spark.md",
    "executors/contracts-oss-lakehouse.md",
    "executors/contracts-oss-clickhouse.md",
    "executors/contracts-oss-debezium.md",
    "executors/contracts-oss-pulsar.md",
    "executors/contracts-oss-starrocks.md",
    "executors/contracts-oss-doris.md",
    "datasources/metatable-lifecycle.md",
    "datasources/metatable-types.md",
    "knowledge/faq-troubleshooting.md",
    "knowledge/routing-outbound.md",
    "knowledge/link-parsing.md",
    "evals/evals-router.json",
    "evals/evals-dev.json",
    "evals/evals-ops.json",
    "evals/evals-safety.json",
    "evals/evals-contract.json",
    "tests/test_engine.py",
    "tests/test_hooks.py",
    "tests/test_repo_invariants.py",
    "templates/config.example.json",
    "templates/lab.example.json",
    "docs/validation-report.md",
    "tools/desensitize_terms.example.txt",
    "tools/adapt_hooks.py",
    "tools/build_codex_surface.py",
    "tools/run_evals.py",
    "tools/score_inspection.py",
    "tools/awr_reports.py",
    "tools/oss_cli.py",
    "tools/oss_lab.py",
    "tools/lab/spark_lakehouse_smoke.py",
    "tools/lab/spark_streaming_smoke.py",
    "tools/lab/debezium_cdc_smoke.sh",
    "tools/lab/serving_cluster_up.sh",
    "tools/lab/serving_smoke.sh",
    "tests/test_oss_lab.py",
    "tests/fixtures/inspection-snapshot.json",
    "tests/test_score_inspection.py",
    "tests/test_oss_cli.py",
    "docs/reports/README.md",
    "docs/host-hooks.md",
    "docs/oss-component-ledger.md",
    "docs/apache-readiness-audit.md",
    "docs/decisions/README.md",
    "README.en.md",
    "docs/release-process.md",
    "docs/glossary.md",
    "docs/README.md",
    "docs/third-party-dependencies.md",
    "NOTICE",
    "GOVERNANCE.md",
    "CODE_OF_CONDUCT.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug.md",
    ".github/ISSUE_TEMPLATE/feature.md",
    ".github/ISSUE_TEMPLATE/config-help.md",
]

# 第 4 项：执行器契约里不许出现业务叙事词；工作流里不许内联命令串
BUSINESS_WORDS = ["场景一", "场景二", "迁移参数确认", "SLA 决策"]
# 引擎自己的调用（py -3 .rtd/engine/rtd.py …）不算"内联平台命令"——工作流本来就要调引擎。
# 引擎调用（.rtd/engine/rtd.py）与包内工具（tools/*.py）不算"内联平台命令"：
# 工作流本来就要调这两类；禁的是把平台自己的命令串抄进工作流。
COMMAND_PATTERNS = [
    r"`[a-z][a-z0-9_-]*\s+(install|start|stop|deploy|submit|publish)\b",
    r"\bpy -3\s+(?!\.rtd/engine/rtd\.py|tools/)",
    r"\bpython3\s+(?!\.rtd/engine/rtd\.py|tools/)",
]

SKILL_ROOTS = [
    Path.home() / ".codex" / "skills",
    Path.home() / ".agents" / "skills",
]
# 插件形态安装的技能：<cache>/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md
PLUGIN_CACHE_GLOBS = [
    Path.home() / ".codex" / "plugins" / "cache" / "*" / "*" / "*" / "skills" / "*" / "SKILL.md",
    Path.home() / ".codex" / "plugins" / "cache" / "*" / "*" / "skills" / "*" / "SKILL.md",
    Path.home() / ".agents" / "plugins" / "cache" / "*" / "*" / "*" / "skills" / "*" / "SKILL.md",
]


def walk_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def check_structure() -> list[str]:
    """第 1 项：文件树 + 两项配置完整性（RTD-019）。

    这两条原先靠人记：CI 是不是真的跑了脱敏与 evals 校验、未脱敏原稿有没有被挡住。
    靠人记的防护等于没有防护，所以放进校验器。
    """
    errors = [f"缺文件：{p}" for p in REQUIRED_PATHS if not (ROOT / p).exists()]

    gitignore = read_text(ROOT / ".gitignore")
    for pattern in (".rtd/", "plan.raw.md"):
        if pattern not in gitignore:
            errors.append(f".gitignore 缺排除项：{pattern}（真实名称会随提交外泄）")

    ci = read_text(ROOT / ".github" / "workflows" / "ci.yml")
    for script in ("tools/validate_plugin.py", "tools/run_evals.py", "tools/build_codex_surface.py"):
        if script not in ci:
            errors.append(f"CI 没有跑 {script}")
    errors.extend(check_hooks_files())
    errors.extend(check_claude_manifest_hooks())
    errors.extend(check_license_headers())
    return errors


def check_claude_manifest_hooks() -> list[str]:
    """Claude 清单不要再声明标准的 hooks 文件。

    宿主**自动加载** `hooks/hooks.json`；清单里再指同一个文件会被判重复，
    结果是**整个插件加载失败**（RTD-020 实测：`Duplicate hooks file detected`，
    `claude plugin list` 显示 `× failed to load`）。该字段只用于引用**额外的** hook 文件。
    """
    path = ROOT / ".claude-plugin" / "plugin.json"
    if not path.is_file():
        return ["缺 .claude-plugin/plugin.json"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        return [f".claude-plugin/plugin.json 不是合法 JSON：{err}"]
    declared = str(manifest.get("hooks") or "").strip().lstrip("./")
    if declared == "hooks/hooks.json":
        return [".claude-plugin/plugin.json 声明了 hooks: ./hooks/hooks.json —— "
                "宿主会自动加载这个标准文件，再声明一次会被判重复、整个插件加载失败（RTD-020 实测）；"
                "该字段只用于引用额外的 hook 文件"]
    return []


LICENSE_HEADER_MARK = "Apache License, Version 2.0"


def check_license_headers() -> list[str]:
    """第 1 项的另一半：自研源码逐文件带 Apache-2.0 许可头。

    只管**本仓库自己写的**代码（引擎、hook、工具、测试）。生成物 `skills/` 由 `commands/`
    生成，加了头会被生成器覆盖；第三方文本有自己的声明，见 `NOTICE` 与
    `docs/third-party-dependencies.md`。
    """
    errors: list[str] = []
    for folder, suffixes in (("engine", (".py",)), ("hooks", (".py",)),
                             ("tools", (".py", ".sh")), ("tests", (".py",))):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if LICENSE_HEADER_MARK not in read_text(path)[:1500]:
                errors.append(f"{rel(path)} 缺 Apache-2.0 许可头（自研源码逐文件声明）")
    return errors


HOOK_EVENTS = ("PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit",
               "SubagentStart", "SubagentStop", "PreCompact", "PostCompact", "PermissionRequest")


def check_hooks_files() -> list[str]:
    """hook 配置文件必须能被宿主认出来。

    踩过的坑：Codex 的 hooks 文件顶层必须包一层 `hooks`；少了它宿主识别到 0 个钩子，
    既不报错也不弹信任提示，属于静默失效。这条检查专门拦它。
    """
    errors: list[str] = []
    for name in ("hooks/hooks.json", "hooks/codex-hooks.json"):
        path = ROOT / name
        if not path.is_file():
            errors.append(f"缺 hook 配置：{name}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            errors.append(f"{name} 不是合法 JSON：{err}")
            continue
        if not isinstance(data, dict) or "hooks" not in data:
            errors.append(f"{name} 顶层缺 `hooks` 包裹（宿主会识别到 0 个钩子且不报错）")
            continue
        events = data["hooks"]
        if not isinstance(events, dict) or not events:
            errors.append(f"{name} 的 hooks 段为空")
            continue
        for event, entries in events.items():
            if event not in HOOK_EVENTS:
                errors.append(f"{name} 事件名不认识：{event}（宿主用 PascalCase）")
                continue
            if not isinstance(entries, list) or not entries:
                errors.append(f"{name} 的 {event} 没有条目")
                continue
            for index, entry in enumerate(entries):
                commands = entry.get("hooks") if isinstance(entry, dict) else None
                if not isinstance(commands, list) or not commands:
                    errors.append(f"{name} 的 {event}[{index}] 缺 hooks 命令数组")
                    continue
                for command in commands:
                    if not isinstance(command, dict) or not str(command.get("command") or "").strip():
                        errors.append(f"{name} 的 {event}[{index}] 有命令条目没有 command")
    return errors


def check_links() -> list[str]:
    errors: list[str] = []
    pattern = re.compile(r"\]\(([^)\s]+)\)")
    for path in walk_files():
        if path.suffix.lower() != ".md":
            continue
        for target in pattern.findall(read_text(path)):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            if not (path.parent / clean).resolve().exists():
                errors.append(f"{rel(path)} → 链接目标不存在：{target}")
    return errors


def check_capability_matrix() -> list[str]:
    matrix = ROOT / "governance" / "capability-matrix.json"
    if not matrix.is_file():
        return ["缺 governance/capability-matrix.json"]
    try:
        data = json.loads(matrix.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        return [f"capability-matrix.json 不是合法 JSON：{err}"]

    errors: list[str] = []
    text = json.dumps(data, ensure_ascii=False)
    for ref in re.findall(r"[A-Za-z0-9_./-]+\.(?:md|json)", text):
        if ref.startswith(".") or "/" not in ref:
            continue
        if not (ROOT / ref).exists():
            errors.append(f"capability-matrix 引用了不存在的文件：{ref}")
    errors.extend(check_registry_consistency())
    return errors


def check_registry_consistency() -> list[str]:
    """第 3 项的另一半：组件注册表 ↔ 执行器契约 ↔ 能力矩阵必须一一对上。

    RTD-038 之前，开源执行器的清单一共有三份：引擎里手写的一份、契约文档、能力矩阵。
    加一个组件要同时改四处，且没有任何检查把它们绑在一起——注册表一扩必然漂移。
    这条检查把三份绑死：tier 1/2 的组件必须有契约、必须在能力矩阵里；反过来，
    能力矩阵里的 oss_* 也必须在注册表里，不许出现在一边、缺在另一边。
    """
    registry_path = ROOT / "governance" / "oss-components.json"
    if not registry_path.is_file():
        return ["缺 governance/oss-components.json"]
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        return [f"oss-components.json 不是合法 JSON：{err}"]
    components = registry.get("components")
    if not isinstance(components, list) or not components:
        return ["oss-components.json 里没有 components 列表"]

    try:
        matrix = json.loads((ROOT / "governance" / "capability-matrix.json").read_text(encoding="utf-8"))
        matrix_executors = matrix.get("executors") if isinstance(matrix.get("executors"), dict) else {}
    except (OSError, json.JSONDecodeError):
        matrix_executors = {}

    errors: list[str] = []
    seen: set[str] = set()
    for item in components:
        if not isinstance(item, dict):
            errors.append("oss-components.json 里有不是对象的组件条目")
            continue
        name = item.get("id")
        if not isinstance(name, str) or not name:
            errors.append("oss-components.json 里有组件缺 id")
            continue
        if name in seen:
            errors.append(f"组件 id 重复：{name}")
        seen.add(name)
        tier = item.get("tier")
        if tier not in {1, 2, 3}:
            errors.append(f"{name} 的 tier 不是 1/2/3：{tier!r}")
        if item.get("launch_mode") not in {"service", "library"}:
            errors.append(f"{name} 的 launch_mode 不是 service/library：{item.get('launch_mode')!r}")
        if item.get("config_ref") != f"executors.{name}":
            errors.append(f"{name} 的 config_ref 与 id 对不上：{item.get('config_ref')!r}")
        if tier in {1, 2}:
            keys = item.get("required_keys")
            if not isinstance(keys, list) or not keys:
                errors.append(f"{name} 是 tier {tier}，required_keys 不能为空（“已配置”的判定靠它）")
            contract = item.get("contract_ref") or f"executors/contracts-{name.replace('_', '-')}.md"
            if not (ROOT / str(contract)).exists():
                errors.append(f"{name} 缺执行器契约：{contract}")
            if name not in matrix_executors:
                errors.append(f"{name} 没有登记进 capability-matrix.json 的 executors")
            if item.get("launch_mode") == "service":
                ready = item.get("ready") or {}
                if not (ready.get("tcp") or ready.get("http") or ready.get("probe_argv")):
                    errors.append(f"{name} 是 service 形态但没有就绪探针（会起成“不知道好没好”）")
        if tier == 3 and item.get("start"):
            errors.append(f"{name} 是 tier 3（只登记角色与配置形状），不该带本地启动配方")

    for name in matrix_executors:
        if str(name).startswith("oss_") and name not in seen:
            errors.append(f"capability-matrix.json 里的 {name} 没登记进 oss-components.json")
    return errors


def check_layer_purity() -> list[str]:
    """第 4 项：分层纯度 + 引擎调用一致性。

    * executors/ 只写契约，不写业务叙事；
    * workflows/ 不内联平台命令串（引擎调用除外）；
    * commands/ 与 workflows/ 里出现的 `.rtd/engine/rtd.py <子命令> --flag` 必须真实存在——
      文档写了引擎不认的参数，跟着做的人会直接吃报错（踩过一次）。
    """
    errors: list[str] = []
    for path in (ROOT / "executors").glob("*.md") if (ROOT / "executors").is_dir() else []:
        text = read_text(path)
        for word in BUSINESS_WORDS:
            if word in text:
                errors.append(f"{rel(path)} 出现业务叙事词「{word}」（应只写执行器契约）")
    for path in (ROOT / "workflows").glob("*.md") if (ROOT / "workflows").is_dir() else []:
        text = read_text(path)
        for pattern in COMMAND_PATTERNS:
            hit = re.search(pattern, text)
            if hit:
                errors.append(f"{rel(path)} 内联了命令串「{hit.group(0)}」（应引用 executors/）")
    errors.extend(check_engine_invocations())
    return errors


def check_engine_invocations(extra_folder: Path | None = None) -> list[str]:
    """文档里的引擎调用必须能被引擎自己的解析器接受。

    `extra_folder` 供测试注入一个临时目录，便于验证"写了引擎不认的参数会被抓"。
    """
    errors: list[str] = []
    parser = _engine_parser()
    if parser is None:
        # 不能静默通过：检查没跑起来，和检查通过是两回事（CI 上踩过一次）。
        detail = f"（{ENGINE_PARSER_ERROR}）" if ENGINE_PARSER_ERROR else ""
        return [f"无法加载引擎解析器，引擎调用一致性未校验{detail}——请检查 engine/rtd.py 能否被导入"]
    known_subcommands = _subcommands(parser)
    pattern = re.compile(r"rtd\.py\s+([a-z-]+)((?:\s+--?[A-Za-z0-9_-]+)*)")
    bases = [ROOT / "commands", ROOT / "workflows"]
    if extra_folder is not None:
        bases.append(extra_folder)
    for base in bases:
        for path in sorted(base.glob("*.md")) if base.is_dir() else []:
            for subcommand, flags in pattern.findall(read_text(path)):
                if subcommand not in known_subcommands:
                    errors.append(f"{rel(path)} 调用不存在的子命令：rtd.py {subcommand}")
                    continue
                allowed = _option_strings(parser, subcommand)
                for flag in flags.split():
                    if flag.startswith("--") and flag not in allowed:
                        errors.append(f"{rel(path)} 用了引擎不认的参数：rtd.py {subcommand} {flag}")
    return errors


ENGINE_PARSER_ERROR = ""


class Skip:
    """标记"本机无法判定"，与"检查失败"区分开。

    出站路由指向的插件装没装，只有本机知道；CI runner 上什么都没装，
    这时把"不知道"当成"不存在"会误报（实测在 GitHub Actions 上就红在这条）。
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason


def _engine_parser():
    global ENGINE_PARSER_ERROR
    engine_dir = ROOT / "engine"
    if not (engine_dir / "rtd.py").is_file():
        ENGINE_PARSER_ERROR = f"缺文件：{engine_dir / 'rtd.py'}"
        return None
    sys.path.insert(0, str(engine_dir))
    try:
        import rtd  # type: ignore

        return rtd.build_parser()
    except Exception as exc:
        ENGINE_PARSER_ERROR = f"{type(exc).__name__}: {exc}"
        return None


def _subcommands(parser) -> set[str]:
    names: set[str] = set()
    for action in parser._actions:
        if hasattr(action, "choices") and isinstance(action.choices, dict):
            names.update(str(key) for key in action.choices)
    return names


def _option_strings(parser, subcommand: str) -> set[str]:
    """递归收集该子命令（含其嵌套子命令）能接受的 option 字符串。"""
    allowed = set()
    for action in parser._actions:
        if not (hasattr(action, "choices") and isinstance(action.choices, dict)):
            continue
        subparser = action.choices.get(subcommand)
        if subparser is None:
            continue
        stack = [subparser]
        while stack:
            current = stack.pop()
            for act in current._actions:
                allowed.update(act.option_strings)
                if hasattr(act, "choices") and isinstance(act.choices, dict):
                    stack.extend(act.choices.values())
    return allowed


def check_version_single_source() -> list[str]:
    claude = ROOT / ".claude-plugin" / "plugin.json"
    codex = ROOT / ".codex-plugin" / "plugin.json"
    errors: list[str] = []
    try:
        base = str(json.loads(claude.read_text(encoding="utf-8"))["version"]).strip()
    except (OSError, KeyError, json.JSONDecodeError) as err:
        return [f"读不到 .claude-plugin/plugin.json 的 version：{err}"]

    try:
        codex_version = str(json.loads(codex.read_text(encoding="utf-8"))["version"])
    except (OSError, KeyError, json.JSONDecodeError) as err:
        return [f"读不到 .codex-plugin/plugin.json 的 version：{err}"]

    if not codex_version.startswith(base):
        errors.append(f"版本不一致：claude={base} codex={codex_version}")

    changelog = read_text(ROOT / "CHANGELOG.md")
    if f"## {base}" not in changelog:
        errors.append(f"CHANGELOG.md 缺 `## {base}` 小节")

    for path in walk_files():
        if path.suffix.lower() != ".json" or path.name in {"plugin.json"}:
            continue
        for version in re.findall(r'"version"\s*:\s*"([^"]+)"', read_text(path)):
            if version != base:
                errors.append(f"{rel(path)} 手写了版本号 {version}（唯一版本源是 .claude-plugin/plugin.json）")
    return errors


def check_frontmatter() -> list[str]:
    errors: list[str] = []
    skills_dir = ROOT / "skills"
    if not skills_dir.is_dir():
        return errors
    for skill in sorted(skills_dir.glob("*/SKILL.md")):
        text = read_text(skill)
        if not text.startswith("---"):
            errors.append(f"{rel(skill)} 缺 YAML frontmatter")
            continue
        block = text.split("---", 2)[1] if text.count("---") >= 2 else ""
        name = re.search(r"^name:\s*(.+)$", block, re.M)
        desc = re.search(r"^description:\s*(.+)$", block, re.M)
        if not name or not name.group(1).strip():
            errors.append(f"{rel(skill)} frontmatter 缺 name")
        elif len(name.group(1).strip()) > 64:
            errors.append(f"{rel(skill)} name 超过 64 字符")
        if not desc or not desc.group(1).strip():
            errors.append(f"{rel(skill)} frontmatter 缺 description")
        elif len(desc.group(1)) > 1024:
            errors.append(f"{rel(skill)} description 超过 1024 字符")
    return errors


def load_terms() -> list[str]:
    """脱敏词表按"本地私有文件 → 环境变量"的顺序找。

    词表里写的是真实内部代号，**不能随仓库公开**（公开词表等于公开要藏的名字）。
    所以：本地放 `tools/desensitize_terms.txt`（已 gitignore），CI 用仓库 secret 注入同名文件，
    两边都没有时这项检查跳过而不是报错——但要在输出里说清"没检查"，不许静默算通过。
    """
    env_terms = os.environ.get("RTD_DESENSITIZE_TERMS", "")
    if env_terms.strip():
        return [line.strip() for line in env_terms.splitlines() if line.strip() and not line.strip().startswith("#")]

    terms: list[str] = []
    for line in read_text(TERMS_FILE).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def check_desensitize() -> list:
    terms = load_terms()
    if not terms:
        return [Skip(
            "没有脱敏词表：本地缺 tools/desensitize_terms.txt 且未设置 RTD_DESENSITIZE_TERMS；"
            "格式见 tools/desensitize_terms.example.txt（词表本身不入仓库）"
        )]
    errors: list[str] = []
    for path in walk_files():
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        text = read_text(path)
        lowered = text.lower()
        for term in terms:
            if term.lower() in lowered:
                errors.append(f"{rel(path)} 命中脱敏词「{term}」")
    return errors


def check_routing(roots: list[Path] | None = None, patterns: list[Path] | None = None) -> list:
    path = ROOT / "knowledge" / "routing-outbound.md"
    if not path.is_file():
        return []
    roots = SKILL_ROOTS if roots is None else roots
    patterns = PLUGIN_CACHE_GLOBS if patterns is None else patterns
    installed = _installed_skill_pairs(patterns)
    installed_plugins = {name.split(":", 1)[0] for name in installed}

    # 既没有技能根目录、也没有任何插件缓存 → 本机根本没装技能包（CI/新机器），无法判定。
    if not any(item.is_dir() for item in roots) and not installed:
        return [Skip("本机没有任何技能根目录（CI 或新机器），出站路由存在性无法判定；这条只在本地生效")]

    errors: list[str] = []
    for name in set(re.findall(r"`([a-z][a-z0-9-]*:[a-z0-9-]+)`", read_text(path))):
        plugin, _skill = name.split(":", 1)
        if name in installed or plugin in installed_plugins:
            continue
        if not any((root / plugin / "SKILL.md").exists() or (root / plugin).is_dir() for root in roots):
            errors.append(f"routing-outbound.md 指向未安装的技能包：{name}")
    return errors


def _installed_skill_pairs(patterns: list[Path] | None = None) -> set[str]:
    pairs: set[str] = set()
    for pattern in (PLUGIN_CACHE_GLOBS if patterns is None else patterns):
        for match in (Path(item) for item in glob(str(pattern.expanduser()).replace("\\", "/"))):
            parts = match.parts
            if "skills" not in parts:
                continue
            index = parts.index("skills")
            if index < 1 or index + 1 >= len(parts):
                continue
            skill = parts[index + 1]
            plugin = parts[index - 2] if index >= 2 and _looks_like_version(parts[index - 1]) else parts[index - 1]
            pairs.add(f"{plugin}:{skill}")
    return pairs


def _looks_like_version(value: str) -> bool:
    return bool(re.match(r"^\d", value)) or "+codex" in value


CHECKS = [
    ("1 文件树完整性", check_structure),
    ("2 链接目标存在", check_links),
    ("3 capability-matrix 引用一致性", check_capability_matrix),
    ("4 分层纯度", check_layer_purity),
    ("5 版本号单源", check_version_single_source),
    ("6 frontmatter 规范", check_frontmatter),
    ("7 脱敏词表零命中", check_desensitize),
    ("8 出站路由可触发", check_routing),
]


def main() -> int:
    global ROOT
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        ROOT = Path(sys.argv[1]).resolve()
    failed = 0
    for label, fn in CHECKS:
        errors = fn()
        skips = [item for item in errors if isinstance(item, Skip)]
        errors = [item for item in errors if not isinstance(item, Skip)]
        if skips and not errors:
            print(f"[SKIP] {label} —— {skips[0].reason}")
            continue
        if errors:
            failed += 1
            print(f"[FAIL] {label}")
            for err in errors[:20]:
                print(f"       - {err}")
            if len(errors) > 20:
                print(f"       … 共 {len(errors)} 条")
        else:
            print(f"[ OK ] {label}")
    print()
    print(f"校验目录：{ROOT}")
    print("结果：全部通过" if not failed else f"结果：{failed} 项未通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
