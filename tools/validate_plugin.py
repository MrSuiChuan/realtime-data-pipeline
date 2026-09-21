#!/usr/bin/env python3
"""八项静态校验（plan.md 第十章的落地实现）。

    py -3 tools/validate_plugin.py .        # Windows
    python3 tools/validate_plugin.py .      # macOS/Linux

退出码：0 = 全过；1 = 有校验失败。
第 7 项（脱敏）是硬红线：命中即失败，不给白名单例外。
"""

from __future__ import annotations

import json
import re
import sys
from glob import glob
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".tmp", ".rtd", "logs", "node_modules"}
# plan.raw.md 是未脱敏原稿，本地私有（.gitignore 已排除），不参与扫描。
SKIP_FILES = {"desensitize_terms.txt", "plan.raw.md"}

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
    "hooks/claude-codex-hooks.json",
    "governance/safety-constitution.md",
    "governance/executor-arbitration.md",
    "governance/identity-and-time.md",
    "governance/response-contracts.md",
    "governance/anti-patterns.md",
    "governance/mcp-setup.md",
    "governance/capability-matrix.json",
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
    "docs/validation-report.md",
    "tools/desensitize_terms.txt",
    "tools/adapt_hooks.py",
    "tools/build_codex_surface.py",
]

# 第 4 项：执行器契约里不许出现业务叙事词；工作流里不许内联命令串
BUSINESS_WORDS = ["场景一", "场景二", "迁移参数确认", "SLA 决策"]
# 引擎自己的调用（py -3 .rtd/engine/rtd.py …）不算"内联平台命令"——工作流本来就要调引擎。
COMMAND_PATTERNS = [
    r"`[a-z][a-z0-9_-]*\s+(install|start|stop|deploy|submit|publish)\b",
    r"\bpy -3\s+(?!\.rtd/engine/rtd\.py)",
    r"\bpython3\s+(?!\.rtd/engine/rtd\.py)",
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
    return errors


def check_layer_purity() -> list[str]:
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
    return errors


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
    path = ROOT / "tools" / "desensitize_terms.txt"
    terms = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def check_desensitize() -> list[str]:
    terms = load_terms()
    if not terms:
        return ["脱敏词表为空：tools/desensitize_terms.txt"]
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


def check_routing() -> list[str]:
    path = ROOT / "knowledge" / "routing-outbound.md"
    if not path.is_file():
        return []
    installed = _installed_skill_pairs()
    installed_plugins = _installed_plugin_names()
    errors: list[str] = []
    for name in set(re.findall(r"`([a-z][a-z0-9-]*:[a-z0-9-]+)`", read_text(path))):
        plugin, _skill = name.split(":", 1)
        if name in installed or plugin in installed_plugins:
            continue
        if not any((root / plugin / "SKILL.md").exists() or (root / plugin).is_dir() for root in SKILL_ROOTS):
            errors.append(f"routing-outbound.md 指向未安装的技能包：{name}")
    return errors


def _installed_plugin_names() -> set[str]:
    return {name.split(":", 1)[0] for name in _installed_skill_pairs()}


def _installed_skill_pairs() -> set[str]:
    pairs: set[str] = set()
    for pattern in PLUGIN_CACHE_GLOBS:
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
    failed = 0
    for label, fn in CHECKS:
        errors = fn()
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
