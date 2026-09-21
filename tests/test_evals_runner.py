"""evals 跑分器的自测：结构校验、导出、汇总三件事都要能拦住错的输入。"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "tools"))

import run_evals  # noqa: E402


def _capture(fn, *args) -> tuple[int, str]:
    buf = io.StringIO()
    argv = sys.argv
    sys.argv = ["run_evals.py", *args]
    try:
        with contextlib.redirect_stdout(buf):
            code = fn()
    except SystemExit as err:
        code = int(err.code or 0)
    finally:
        sys.argv = argv
    return code, buf.getvalue()


def test_check_passes_on_real_suites():
    suites = run_evals.load_suites()
    assert suites, "应至少有一套 evals"
    assert run_evals.check(suites) == []
    assert sum(len(s.get("cases") or []) for s in suites) >= 20


def test_check_catches_structural_problems():
    bad = [{
        "_file": "evals-bad.json",
        "suite": "bad",
        "purpose": "",
        "cases": [
            {"prompt": "p", "expected_output": "", "expectations": []},
            {"prompt": "p", "expected_output": "x", "expectations": [""]},
        ],
    }]
    problems = run_evals.check(bad)
    assert any("purpose" in p for p in problems)
    assert any("expectations" in p for p in problems)
    assert any("expected_output" in p for p in problems)
    assert any("重复" in p for p in problems)


def test_export_contains_every_case():
    suites = run_evals.load_suites()
    text = run_evals.export_markdown(suites)
    for suite in suites:
        for index in range(len(suite["cases"])):
            assert f"### {suite['suite']}#{index}" in text


def test_score_requires_note_for_failures_and_full_coverage():
    suites = run_evals.load_suites()
    keys = [f"{s['suite']}#{i}" for s in suites for i in range(len(s["cases"]))]
    partial = {keys[0]: {"pass": False}}
    problems, report = run_evals.summarize(suites, partial)
    assert any("note" in p for p in problems)
    assert any("缺评分" in p for p in problems)
    assert "0/1" not in report  # 总计行应反映全部用例数

    full = {key: {"pass": True} for key in keys}
    problems, report = run_evals.summarize(suites, full)
    assert problems == []
    assert "100%" in report


def test_cli_modes_run():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "score.md"
        code, text = _capture(run_evals.main, "--export", str(out))
        assert code == 0, text
        assert out.is_file()

        scored = Path(tmp) / "scored.json"
        scored.write_text(json.dumps({"router#0": {"pass": True}}), encoding="utf-8")
        code, text = _capture(run_evals.main, "--score", str(scored))
        assert code == 1  # 只评了一条，其余缺评分必须报出来
        assert "缺评分" in text


if __name__ == "__main__":
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
    print()
    print("evals 跑分器测试：全部通过" if not failures else f"evals 跑分器测试：{failures} 个失败")
    raise SystemExit(1 if failures else 0)
