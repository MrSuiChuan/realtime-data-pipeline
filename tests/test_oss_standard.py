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
"""开源标准（Apache 风格）的机器检查：文件齐全 / 许可一致 / 许可头 / 无个人路径。

为什么单独一份：本仓库既有的 ``tools/validate_plugin.py`` 查的是"插件结构与脱敏"，
``tests/test_repo_invariants.py`` 查的是"生成物与版本一致"。开源标准这一摊原先只有人工审计
（docs/apache-readiness-audit.md），没有防回归——这三件套插件里另外两个各有一份，
本文件把它补齐，口径与它们相同。

判据都写成"故意破坏会红"的形式（见每个用例里的反例）。
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PATHS = (
    "LICENSE",
    "NOTICE",
    "README.md",
    "README.en.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "GOVERNANCE.md",
    "SECURITY.md",
    "SUPPORT.md",
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug.md",
    ".github/ISSUE_TEMPLATE/feature.md",
    ".github/ISSUE_TEMPLATE/config-help.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    "docs/README.md",
    "docs/glossary.md",
    "docs/release-process.md",
    "docs/third-party-dependencies.md",
    "docs/apache-readiness-audit.md",
)

LICENSE_HEADER_MARK = "Apache License, Version 2.0"
HEADER_FOLDERS = (("engine", (".py",)), ("hooks", (".py",)), ("tools", (".py", ".sh")), ("tests", (".py",)))
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".tmp", ".awr", ".rtd", "node_modules"}

POSIX_HOME = re.compile(r"/home/([a-z][a-z0-9_-]*)/")
WINDOWS_HOME = re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+")
# 占位用户名不算个人路径（测试与文档里刻意写的假名字）。
HOME_PLACEHOLDERS = {"u", "lab", "user", "username", "example", "test", "me", "you", "youruser", "someone"}


def _is_redacted(segment: str) -> bool:
    """已脱敏的写法不算泄漏：``C:\\Users\\...\\``、``<username>``、``%USERNAME%``。

    本仓库的 docs/validation-report.md 里引用了一段宿主报错原文，写的就是
    ``C:\\Users\\...\\realtime-data-plugin\\hooks\\hooks.json``——那是脱敏后的证据，
    一刀切会把已有内容误判成新泄漏。
    """
    return "..." in segment or segment.startswith("<") or segment.startswith("%")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _tracked_text_files(root: Path) -> list:
    out = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        if path.suffix in (".png", ".jpg", ".ico", ".pdf", ".pyc"):
            continue
        out.append(path)
    return out


def missing_required_paths(root: Path = ROOT) -> list:
    return [name for name in REQUIRED_PATHS if not (root / name).is_file()]


def license_mismatches(root: Path = ROOT) -> list:
    errors = []
    if "Apache License" not in _read(root / "LICENSE"):
        errors.append("LICENSE 不是 Apache-2.0 全文")
    notice = _read(root / "NOTICE")
    match = re.search(r"Copyright(?: \(c\))? \d{4} (.+)", notice)
    owner = match.group(1).strip() if match else ""
    if not owner:
        errors.append("NOTICE 里找不到 Copyright 行")
    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        data = json.loads(_read(root / rel))
        if data.get("license") != "Apache-2.0":
            errors.append(f"{rel} 的 license 是 {data.get('license')!r}，应为 'Apache-2.0'")
        author = (data.get("author") or {}).get("name")
        if owner and author != owner:
            errors.append(f"{rel} 的署名 {author!r} 与 NOTICE 的 {owner!r} 不一致")
    return errors


def missing_license_headers(root: Path = ROOT) -> list:
    errors = []
    for folder, suffixes in HEADER_FOLDERS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes or "__pycache__" in path.parts:
                continue
            if LICENSE_HEADER_MARK not in _read(path)[:1500]:
                errors.append(f"{path.relative_to(root).as_posix()} 缺 Apache-2.0 许可头")
    return errors


def personal_paths(root: Path = ROOT) -> list:
    errors = []
    for path in _tracked_text_files(root):
        text = _read(path)
        hit = POSIX_HOME.search(text)
        if hit and hit.group(1) not in HOME_PLACEHOLDERS:
            errors.append(f"{path.relative_to(root).as_posix()} 含 POSIX 本机绝对路径：{hit.group(0)!r}")
            continue
        hit = WINDOWS_HOME.search(text)
        if hit and not _is_redacted(hit.group(0)):
            errors.append(f"{path.relative_to(root).as_posix()} 含 Windows 本机绝对路径：{hit.group(0)!r}")
    return errors


# --------------------------------------------------------------------------------------
# 正例：本仓库现在必须全过
# --------------------------------------------------------------------------------------


def test_required_paths_are_all_present() -> None:
    assert missing_required_paths() == []


def test_license_and_signature_agree_everywhere() -> None:
    assert license_mismatches() == []


def test_every_source_file_has_a_license_header() -> None:
    assert missing_license_headers() == []


def test_no_personal_paths_in_tracked_files() -> None:
    assert personal_paths() == []


# --------------------------------------------------------------------------------------
# 反例：把判据故意破坏，必须报出来（否则这道检查就是摆设）
# --------------------------------------------------------------------------------------


def test_missing_file_is_reported() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        errors = missing_required_paths(Path(tmp))
    assert "SUPPORT.md" in errors and "LICENSE" in errors


def test_missing_license_header_is_reported() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "engine").mkdir()
        (root / "engine" / "fresh.py").write_text("print('no header')\n", encoding="utf-8")
        errors = missing_license_headers(root)
    assert errors == ["engine/fresh.py 缺 Apache-2.0 许可头"], errors


def test_real_looking_home_path_is_reported_but_placeholder_is_not() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ok.md").write_text("home: /home/u/oss/flink\n", encoding="utf-8")
        (root / "bad.md").write_text("home: /home/realsomeone/oss/flink\n", encoding="utf-8")
        errors = personal_paths(root)
    assert len(errors) == 1 and "bad.md" in errors[0], errors
