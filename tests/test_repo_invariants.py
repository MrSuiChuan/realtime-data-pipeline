"""仓库级不变量：清单可解析、版本单源、脱敏词表真的在拦人。

这几条是最小可信集：它们坏了，后面所有校验都不可信。
"""

from __future__ import annotations

import json
import sys
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


ROOT = Path(__file__).resolve().parent.parent


def _json(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_manifests_share_one_version():
    claude = _json(".claude-plugin/plugin.json")
    codex = _json(".codex-plugin/plugin.json")
    assert claude["name"] == codex["name"] == "realtime-data-plugin"
    assert codex["version"].startswith(claude["version"])


def test_desensitize_terms_are_present_and_not_empty():
    terms = [
        line.strip()
        for line in (ROOT / "tools" / "desensitize_terms.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert terms, "脱敏词表为空"
    assert len(set(terms)) == len(terms), "脱敏词表有重复项"


def test_plan_md_has_no_denied_terms():
    terms = [
        line.strip()
        for line in (ROOT / "tools" / "desensitize_terms.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    plan = (ROOT / "plan.md").read_text(encoding="utf-8").lower()
    hits = [term for term in terms if term.lower() in plan]
    assert not hits, f"plan.md 命中脱敏词：{hits}"


def test_config_example_is_tracked_outside_runtime_dir():
    # .rtd/ 是运行时目录且被 .gitignore 排除，示例配置不能放进去
    assert (ROOT / "templates" / "config.example.json").is_file()
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".rtd/" in ignored


def test_engine_invocations_in_docs_match_the_engine():
    """文档里写的引擎调用必须真实存在——写错过一次（setup --report）。"""
    import tempfile
    from pathlib import Path as _Path

    sys.path.insert(0, str(ROOT / "tools"))
    import validate_plugin

    assert validate_plugin.check_engine_invocations() == []

    with tempfile.TemporaryDirectory() as tmp:
        folder = _Path(tmp)
        (folder / "bad.md").write_text(
            "```\npy -3 .rtd/engine/rtd.py setup --report\npy -3 .rtd/engine/rtd.py frobnicate --x\n```\n",
            encoding="utf-8",
        )
        # 必须在 with 内调用：临时目录一旦回收，扫描就找不到文件，会假通过（踩过）
        problems = validate_plugin.check_engine_invocations(extra_folder=folder)
    assert any("--report" in p for p in problems), problems
    assert any("frobnicate" in p for p in problems), problems


def test_routing_check_skips_when_no_skills_installed():
    """CI/新机器上没有任何技能包时，出站路由检查必须"跳过"，不能判失败。"""
    import tempfile
    from pathlib import Path as _Path

    sys.path.insert(0, str(ROOT / "tools"))
    import validate_plugin

    with tempfile.TemporaryDirectory() as tmp:
        empty_roots = [_Path(tmp) / "skills", _Path(tmp) / "agents-skills"]
        result = validate_plugin.check_routing(roots=empty_roots, patterns=[])
    assert len(result) == 1 and isinstance(result[0], validate_plugin.Skip), result

    # 装了一个插件时：指向它的路由放行，指向另一个仍报错
    with tempfile.TemporaryDirectory() as tmp:
        root = _Path(tmp) / "skills"
        (root / "data-development-plugin").mkdir(parents=True)
        result = validate_plugin.check_routing(roots=[root], patterns=[])
        assert not any(isinstance(item, validate_plugin.Skip) for item in result), result
        messages = "\n".join(str(item) for item in result)
        assert "knowledge-base-plugin:kbp-status" in messages, messages


def test_awr_reports_helper_reads_the_report_dir():
    """RTD-028：报告命名约定要能被工具解析出来，否则人会迷路。"""
    import subprocess

    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "awr_reports.py"), "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["rounds"], "至少应有一个提交轮次"
    assert any(item.startswith("RTD-") for item in payload["items"]), payload["items"].keys()
    for info in payload["items"].values():
        assert info["latest"] in info["all"]


def test_validator_flags_missing_config_guards():
    """RTD-019：校验器必须自己发现"gitignore 漏挡"和"CI 漏跑校验"。"""
    import tempfile
    from pathlib import Path as _Path

    sys.path.insert(0, str(ROOT / "tools"))
    import validate_plugin

    original = validate_plugin.ROOT
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fake = _Path(tmp)
            for rel in validate_plugin.REQUIRED_PATHS:
                target = fake / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x", encoding="utf-8")
            # 故意写一份缺排除项、缺 CI 步骤的仓库
            (fake / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
            ci = fake / ".github" / "workflows" / "ci.yml"
            ci.parent.mkdir(parents=True, exist_ok=True)
            ci.write_text("steps: []\n", encoding="utf-8")
            validate_plugin.ROOT = fake
            problems = validate_plugin.check_structure()
        assert any("plan.raw.md" in p for p in problems)
        assert any(".rtd/" in p for p in problems)
        assert any("validate_plugin.py" in p for p in problems)
        assert any("run_evals.py" in p for p in problems)
    finally:
        validate_plugin.ROOT = original


if __name__ == "__main__":
    # 本地没装 pytest 时直接跑：py -3 tests/test_repo_invariants.py
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"[ OK ] {name}")
        except AssertionError as err:
            failures += 1
            print(f"[FAIL] {name}: {err}")
    raise SystemExit(1 if failures else 0)
