#!/usr/bin/env python3
"""巡检评分：吃一份快照，出一份报告与分数。**不碰网络，不覆盖历史。**

    py -3 tools/score_inspection.py --snapshot snap.json --out ../reports/job_a-20260921T2200

输入是快照 JSON（契约见下），输出是一个**新建目录**，里面 `report.md` + `score.json`。
目录已存在就拒绝——历史报告绝不覆盖。

## 硬拒绝（都会带原因退出，不做"尽力而为"）

* 快照超过 8 MiB；快照不是合法 JSON；**JSON 里有重复键**（重复键会让"看到的值"和"实际的值"不一致）；
* 输出目录已存在；输出目录在插件仓库内部（报告属于项目，不该写回包）；
* `snapshot_version` 不是 1。

## 快照契约（snapshot_version = 1）

```json
{
  "snapshot_version": 1,
  "observed_at": "2026-09-21T22:00:00+08:00",
  "window": {"start": "...", "end": "...", "minutes": 30},
  "object": {"file_id": "F-1", "name": "job_a", "engine": "..."},
  "coverage": {
    "metrics_ratio": 0.95, "metrics_fresh": true, "events_available": true,
    "snapshots_available": true, "resources_available": true, "lineage_available": false,
    "upstream_checked": true, "downstream_checked": true, "blocked": ["lineage:权限不足"]
  },
  "signals": {
    "restarts": {"planned": 0, "unplanned": 2},
    "failovers": {"count": 2, "distinct_ids": 2},
    "backpressure": {"max": 0.85, "samples": 30, "sustained": true},
    "checkpoints": {"failed_in_window": 1, "window_success_rate": 0.95, "last_success_age_min": 4},
    "resources": {"worst_tm_cpu": 0.92, "max_tm_memory": 0.88},
    "layout": {"expected_nodes": 6, "actual_nodes": 6, "missing": [], "unexpected": []},
    "upstream": [{"name": "src_a", "state": "ok", "traffic": "steady", "errors": 0, "impact": "none"}],
    "downstream": [{"name": "sink_a", "state": "degraded", "traffic": "slow", "errors": 3, "impact": "backpressure"}]
  }
}
```

## 评分的诚实边界

* 分数来自**技术启发式阈值**，不是官方健康模型，也没用真实故障窗口校准过；
* 覆盖不齐时给的是**已观测风险暂评分**并夹住上限，且明说"非完整分"；
* 信号缺失记 `unknown`，**不扣分也不判正常**；全无证据不会给出高分；
* 任何写操作都不在本脚本能力范围内——它只出报告。
"""

from __future__ import annotations

import argparse
import json
import os
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
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
PROVISIONAL_CAP = 74
MIN_METRICS_RATIO = 0.90


class Refused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_snapshot(path: Path) -> dict:
    if not path.is_file():
        raise Refused("snapshot_missing", f"快照不存在：{path}")
    size = path.stat().st_size
    if size > MAX_SNAPSHOT_BYTES:
        raise Refused("snapshot_too_large", f"快照 {size} 字节，超过 {MAX_SNAPSHOT_BYTES // 1024 // 1024} MiB")

    duplicates: list[str] = []

    def hook(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                duplicates.append(str(key))
            seen.add(key)
        return dict(pairs)

    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise Refused("snapshot_invalid", f"快照读不出来：{err}") from err
    if duplicates:
        raise Refused("snapshot_duplicate_keys", "快照有重复键：" + "、".join(sorted(set(duplicates))))
    if not isinstance(data, dict):
        raise Refused("snapshot_shape", "快照顶层必须是对象")
    if data.get("snapshot_version") != 1:
        raise Refused("snapshot_version", f"snapshot_version 必须是 1，拿到 {data.get('snapshot_version')!r}")
    return data


def prepare_outdir(out: Path) -> Path:
    resolved = out.expanduser().resolve()
    if resolved.exists():
        raise Refused("outdir_exists", f"输出目录已存在，不覆盖历史：{resolved}")
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise Refused("outdir_inside_plugin", f"输出目录在插件仓库内部，报告不该写回包：{resolved}")
    resolved.mkdir(parents=True, mode=0o700)
    return resolved


CoverageFlag = tuple[str, str, str]  # (字段, 说明, 缺失时的缺口标签)

COVERAGE_FLAGS: tuple[CoverageFlag, ...] = (
    ("metrics_ratio", "连续指标覆盖度", "未采集"),
    ("metrics_fresh", "指标新鲜度（末点距截止 ≤1 个采样周期）", "接口无样本"),
    ("events_available", "事件（重启/异常）", "未采集"),
    ("snapshots_available", "快照/保存点", "未采集"),
    ("resources_available", "资源（CPU/内存）", "未采集"),
    ("lineage_available", "上下游血缘", "能力未发现"),
    ("upstream_checked", "上游依赖核对", "未采集"),
    ("downstream_checked", "下游依赖核对", "未采集"),
)


def gaps_of(snapshot: dict) -> list[str]:
    coverage = snapshot.get("coverage") if isinstance(snapshot.get("coverage"), dict) else {}
    gaps: list[str] = []
    ratio = coverage.get("metrics_ratio")
    if not isinstance(ratio, (int, float)) or ratio < MIN_METRICS_RATIO:
        shown = f"{ratio:.0%}" if isinstance(ratio, (int, float)) else "缺失"
        gaps.append(f"连续指标覆盖度 {shown}，低于 {MIN_METRICS_RATIO:.0%}（未采集/采集不足）")
    for field, label, tag in COVERAGE_FLAGS:
        if field == "metrics_ratio":
            continue
        if coverage.get(field) is not True:
            gaps.append(f"{label}：{tag}")
    for item in coverage.get("blocked") or []:
        gaps.append(f"明确受阻：{item}")
    return gaps


def findings_of(snapshot: dict) -> list[dict]:
    signals = snapshot.get("signals") if isinstance(snapshot.get("signals"), dict) else {}
    findings: list[dict] = []

    def add(severity: str, key: str, title: str, detail: str) -> None:
        findings.append({"severity": severity, "key": key, "title": title, "detail": detail})

    restarts = signals.get("restarts")
    if isinstance(restarts, dict):
        unplanned = int(restarts.get("unplanned") or 0)
        if unplanned >= 3:
            add("高", "restarts", f"窗口内非计划重启 {unplanned} 次", "先按诊断流程定位，不要在原因未明时重启")
        elif unplanned >= 1:
            add("中", "restarts", f"窗口内非计划重启 {unplanned} 次", "核对是否与下游抖动或反压同窗")
    else:
        add("unknown", "restarts", "重启信号缺失", "未采集；缺项不等于正常")

    failovers = signals.get("failovers")
    if isinstance(failovers, dict):
        count = int(failovers.get("count") or 0)
        if count:
            add("中" if count < 3 else "高", "failovers", f"失败切换 {count} 次", "只看当前运行作业，历史作业另算")

    backpressure = signals.get("backpressure")
    if isinstance(backpressure, dict):
        peak = float(backpressure.get("max") or 0)
        if peak >= 0.8 and backpressure.get("sustained"):
            add("高", "backpressure", f"反压持续越线（峰值 {peak:.2f}）", "降采样曲线不能单独作为持续证据，需覆盖度支撑")
        elif peak >= 0.8:
            add("中", "backpressure", f"反压峰值 {peak:.2f}", "需确认是否持续，脉冲不等于持续越线")

    checkpoints = signals.get("checkpoints")
    if isinstance(checkpoints, dict):
        failed = int(checkpoints.get("failed_in_window") or 0)
        rate = checkpoints.get("window_success_rate")
        if failed >= 2 or (isinstance(rate, (int, float)) and rate < 0.95):
            add("高", "checkpoints", f"快照窗口成功率 {rate if rate is not None else '未知'}", f"窗口内失败 {failed} 次")

    resources = signals.get("resources")
    if isinstance(resources, dict):
        cpu = resources.get("worst_tm_cpu")
        mem = resources.get("max_tm_memory")
        if isinstance(cpu, (int, float)) and cpu >= 0.9:
            add("中", "resources", f"最差节点 CPU {cpu:.2f}", "聚合值不等于最差节点，这里取的就是最差")
        if isinstance(mem, (int, float)) and mem >= 0.9:
            add("中", "resources", f"单节点内存 {mem:.2f}", "内存多分支取最大，不做相加")

    layout = signals.get("layout")
    if isinstance(layout, dict):
        missing = layout.get("missing") or []
        if missing:
            add("高", "layout", f"预期节点缺席 {len(missing)} 个", "：" + "、".join(str(x) for x in missing[:5]))

    for side in ("upstream", "downstream"):
        entries = signals.get(side)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            state = str(entry.get("state") or "").lower()
            if state and state not in {"ok", "healthy", "normal", "running"}:
                add("中", side, f"{side} {entry.get('name')} 状态 {entry.get('state')}", f"流量 {entry.get('traffic')}；错误 {entry.get('errors')}")
    return findings


def score_of(findings: list[dict], gaps: list[str]) -> tuple[int, str]:
    score = 100
    for finding in findings:
        score -= {"高": 18, "中": 8, "unknown": 0}.get(finding["severity"], 0)
    if gaps:
        score = min(score, PROVISIONAL_CAP)
    if not findings and not gaps:
        return min(score, 100), "证据齐备，未发现越线信号"
    if gaps:
        return max(min(score, PROVISIONAL_CAP), 0), "已观测风险暂评分（非完整分：覆盖不足）"
    return max(min(score, 99), 0), "已观测风险评分（覆盖齐备，非官方健康模型）"


def render(snapshot: dict, findings: list[dict], gaps: list[str], score: int, label: str) -> str:
    obj = snapshot.get("object") if isinstance(snapshot.get("object"), dict) else {}
    window = snapshot.get("window") if isinstance(snapshot.get("window"), dict) else {}
    ranked = sorted(findings, key=lambda f: {"高": 0, "中": 1, "unknown": 2}.get(f["severity"], 3))
    lines = [
        f"# 巡检报告：{obj.get('name') or obj.get('file_id') or '未命名对象'}",
        "",
        f"- 观测时间：{snapshot.get('observed_at')}",
        f"- 窗口：{window.get('start')} → {window.get('end')}（{window.get('minutes')} 分钟）",
        f"- 分数：**{score}** — {label}",
        f"- 阈值为待校准的技术启发式，不是官方健康模型",
        "",
        "## 关键发现",
        "",
    ]
    if ranked:
        for finding in ranked[:3]:
            lines.append(f"- [{finding['severity']}] {finding['title']}——{finding['detail']}")
    else:
        lines.append("- 无越线信号（覆盖齐备时才可这样写）")
    lines += ["", "## 优先建议", ""]
    advice = [f for f in ranked if f["severity"] in {"高", "中"}][:3]
    if advice:
        for finding in advice:
            lines.append(f"- 先处理 {finding['key']}：{finding['title']}（诊断走 runbook-diagnosis，变更走 runbook-lifecycle）")
    else:
        lines.append("- 无需立即动作；保持常规巡检")
    lines += ["", "## 依赖影响（一层）", ""]
    signals = snapshot.get("signals") if isinstance(snapshot.get("signals"), dict) else {}
    deps = (signals.get("upstream") or []) + (signals.get("downstream") or [])
    if deps:
        for entry in deps[:8]:
            lines.append(f"- {entry.get('name')}：状态 {entry.get('state')}；流量 {entry.get('traffic')}；错误 {entry.get('errors')}；影响 {entry.get('impact')}")
    else:
        lines.append("- 未采集到依赖证据（缺项不等于正常）")
    lines += ["", "## 覆盖范围与缺口", ""]
    if gaps:
        for gap in gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- 覆盖齐备")
    lines += [
        "",
        "## 结论",
        "",
        f"分数 {score}（{label}）。本报告只陈述已采集到的证据；未采集部分按缺口列出，不推断为正常。",
        "任何变更都必须走对应 runbook 并通过当次确认——巡检本身不改任何线上状态。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="巡检评分（离线，只出报告）")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        snapshot = load_snapshot(Path(args.snapshot))
        outdir = prepare_outdir(Path(args.out))
        gaps = gaps_of(snapshot)
        findings = findings_of(snapshot)
        score, label = score_of(findings, gaps)
        report = render(snapshot, findings, gaps, score, label)
    except Refused as err:
        print(json.dumps({"ok": False, "code": err.code, "message": err.message}, ensure_ascii=False, indent=2)
              if args.json else f"[拒绝] {err.message}")
        return 2

    (outdir / "report.md").write_text(report, encoding="utf-8", newline="\n")
    os.chmod(outdir / "report.md", 0o600)
    payload = {
        "ok": True,
        "score": score,
        "label": label,
        "coverage_gaps": gaps,
        "findings": findings,
        "object": snapshot.get("object"),
        "observed_at": snapshot.get("observed_at"),
    }
    (outdir / "score.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.chmod(outdir / "score.json", 0o600)

    if args.json:
        print(json.dumps({"ok": True, "out": str(outdir), "score": score, "label": label,
                          "gaps": len(gaps), "findings": len(findings)}, ensure_ascii=False, indent=2))
    else:
        print(f"报告已写出：{outdir}")
        print(f"分数：{score}（{label}）；缺口 {len(gaps)} 项，发现 {len(findings)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
