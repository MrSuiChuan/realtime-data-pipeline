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
"""重新安装这条路本身也要有回归：版本后缀与 marketplace 路径解析错了会静默装旧副本。"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("rtd_reinstall", ROOT_REPO / "tools" / "reinstall.py")
reinstall = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reinstall)


def test_new_version_replaces_suffix_and_keeps_base() -> None:
    cases = {
        "0.1.0": "0.1.0+codex.tok",
        "0.1.0+codex.old": "0.1.0+codex.tok",
        "1.2.3-beta.1+codex.prev": "1.2.3-beta.1+codex.tok",
    }
    for current, expected in cases.items():
        assert reinstall.new_version(current, "tok") == expected, current


def test_source_path_is_relative_to_home_not_the_marketplace_file() -> None:
    # Codex 的解析口径：~/.agents/plugins/marketplace.json 里的 "./plugins/x"
    # 指向 ~/plugins/x，而不是 ~/.agents/plugins/plugins/x。
    assert reinstall.resolve_source("./plugins/realtime-data-plugin") == (
        Path.home() / "plugins" / "realtime-data-plugin"
    )


def test_drop_migrated_skills_keeps_the_native_skills(monkeypatch) -> None:
    """宿主生成的 source-command-* 与自带的 rtd-* 指的是同一批 commands，必须清掉重复那份。"""
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        monkeypatch.setattr(reinstall, "CACHE_ROOT", cache)
        version = "0.1.0+codex.tok"
        root = cache / "personal" / "realtime-data-plugin" / version
        (root / "skills" / "rtd-dev").mkdir(parents=True)
        (root / reinstall.MIGRATED_SKILLS_DIR / "source-command-dev").mkdir(parents=True)

        removed = reinstall.drop_migrated_skills(version, "realtime-data-plugin")

        assert len(removed) == 1, removed
        assert not (root / reinstall.MIGRATED_SKILLS_DIR).exists()
        assert (root / "skills" / "rtd-dev").is_dir()
