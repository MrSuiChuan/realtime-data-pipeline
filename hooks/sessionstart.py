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

"""SessionStart：有运行时就把"当前在哪、下一步缺什么"顶到眼前。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import emit, load_payload, project_root, trace_payload  # noqa: E402


def main() -> None:
    payload = load_payload()
    trace_payload("SessionStart", payload)
    root = project_root(payload)
    runtime_file = root / ".rtd" / "_state.json"
    if not runtime_file.is_file():
        emit({})
        return

    try:
        import core

        runtime = core.Runtime(root)
        state = runtime.load_state()
        gaps = runtime.phase_gaps(state)
        parts = [f"[realtime-data-plugin] 阶段：{state.get('phase')}"]
        obj = state.get("object") or {}
        if obj.get("name") or obj.get("file_id"):
            parts.append(f"对象：{obj.get('name') or obj.get('file_id')}")
        if gaps:
            parts.append("待补门控：" + "、".join(g["gate"] for g in gaps))
        else:
            parts.append("本阶段门控已齐，可推进")
        recent = runtime.latest_runs(3)
        if recent:
            last = recent[-1]
            parts.append(f"最近执行：{last.get('kind') or last.get('run_id')} → {last.get('status', '进行中')}")
        emit({"systemMessage": "；".join(parts)})
    except Exception as exc:
        emit({"systemMessage": f"[realtime-data-plugin] 状态读取失败：{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()
