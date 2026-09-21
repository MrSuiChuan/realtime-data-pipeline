"""巡检评分的自测：能出报告，也要能拦住四类坏输入。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "score_inspection.py"
FIXTURE = ROOT / "tests" / "fixtures" / "inspection-snapshot.json"


def run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_scores_fixture_and_writes_report():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report-1"
        code, text = run("--snapshot", str(FIXTURE), "--out", str(out), "--json")
        assert code == 0, text
        payload = json.loads(text)
        assert payload["ok"] is True
        # 覆盖有缺口（lineage 缺失 + 明确受阻）→ 暂评分且被夹住上限
        assert payload["score"] <= 74
        assert "暂评分" in payload["label"]
        assert (out / "report.md").is_file() and (out / "score.json").is_file()
        report = (out / "report.md").read_text(encoding="utf-8")
        assert "关键发现" in report and "覆盖范围与缺口" in report
        assert "不是官方健康模型" in report


def test_refuses_existing_outdir():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "exists"
        out.mkdir()
        code, text = run("--snapshot", str(FIXTURE), "--out", str(out), "--json")
        assert code == 2
        assert "不覆盖历史" in text


def test_refuses_outdir_inside_plugin():
    code, text = run("--snapshot", str(FIXTURE), "--out", str(ROOT / ".tmp" / "should-refuse"), "--json")
    assert code == 2
    assert "插件仓库内部" in text


def test_refuses_duplicate_keys():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "dup.json"
        bad.write_text('{"snapshot_version": 1, "object": {}, "object": {"name": "x"}}', encoding="utf-8")
        code, text = run("--snapshot", str(bad), "--out", str(Path(tmp) / "out"), "--json")
        assert code == 2
        assert "重复键" in text


def test_refuses_wrong_version():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "wrong.json"
        bad.write_text(json.dumps({"snapshot_version": 2}), encoding="utf-8")
        code, text = run("--snapshot", str(bad), "--out", str(Path(tmp) / "out"), "--json")
        assert code == 2
        assert "snapshot_version" in text


def test_full_coverage_can_exceed_provisional_cap():
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
        snapshot["coverage"].update({"lineage_available": True, "blocked": []})
        snapshot["signals"]["failovers"] = {"count": 0, "distinct_ids": 0}
        snapshot["signals"]["backpressure"] = {"max": 0.3, "samples": 30, "sustained": False}
        snapshot["signals"]["restarts"] = {"planned": 0, "unplanned": 0}
        snapshot["signals"]["checkpoints"] = {"failed_in_window": 0, "window_success_rate": 1.0, "last_success_age_min": 1}
        snapshot["signals"]["resources"] = {"worst_tm_cpu": 0.4, "max_tm_memory": 0.5}
        snapshot["signals"]["downstream"] = [{"name": "sink_report", "state": "ok", "traffic": "steady", "errors": 0, "impact": "none"}]
        path = Path(tmp) / "clean.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        code, text = run("--snapshot", str(path), "--out", str(Path(tmp) / "out"), "--json")
        assert code == 0, text
        payload = json.loads(text)
        assert payload["score"] > 74
        assert "暂评分" not in payload["label"]


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
    print("评分脚本测试：全部通过" if not failures else f"评分脚本测试：{failures} 个失败")
    raise SystemExit(1 if failures else 0)
