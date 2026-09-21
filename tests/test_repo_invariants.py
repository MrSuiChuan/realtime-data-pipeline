"""仓库级不变量：清单可解析、版本单源、脱敏词表真的在拦人。

这几条是最小可信集：它们坏了，后面所有校验都不可信。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

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
