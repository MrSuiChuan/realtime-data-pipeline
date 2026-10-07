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

"""跨插件契约（**消费端**）：实时数开插件怎么读知识库（记忆）插件写下的索引。

生产端的对应断言在 knowledge-base-plugin 的
`tests/test_engine.py::ConsumerContractTests`。两侧各自对着同一份 schema 断言——
两个单仓 CI 都能钉住这条跨仓库的缝，不需要同时 checkout 两个仓库。

契约（当前实现，两侧必须一起改）：

    <项目根>/.rtd/mock/kb/index.json        ← 本插件自己的运行目录（生产端支持后优先）
    <项目根>/.data-dev/mock/kb/index.json   ← 离线插件的运行目录（生产端当前实际写这里）

    {"documents": [
       {"uri": "viking://resources/domains/<域>/tables/<表>.md",
        "domain": "<域>", "layer": "<表名首段>", "tables": ["<表>"], "abstract": "…"}
    ]}

消费侧只强制 `uri` 以 `knowledge.uri_prefix`（默认 `viking://resources/`）开头；
路径中间那一段两侧写法并不一致（生产端写 `domains/`、消费侧种子数据写 `domain/`），
所以这里**不**断言路径形状——只断言前缀与字段。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "engine"))

import core  # noqa: E402

# 知识库插件发布后，消费侧索引里应当出现的那条记录
PUBLISHED_DOC = {
    "uri": "viking://resources/domains/order/tables/dwd_order_rt.md",
    "domain": "order",
    "layer": "dwd",
    "tables": ["dwd_order_rt"],
    "abstract": "订单实时口径：支付成功才计入；主键 order_id 唯一。",
}


class KnowledgeConsumerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # resolve()：Windows 下 mkdtemp 给的是 8.3 短名（WUZONG~1），
        # 而 Runtime 会把 root 解析成长名，不统一会在比较路径时假失败。
        self.root = Path(self._tmp.name).resolve()
        (self.root / ".rtd").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _publish(self, docs: list[dict], where: str = ".rtd") -> Path:
        """模拟知识库插件同步过来的索引内容。"""
        kb_dir = self.root / where / "mock" / "kb"
        kb_dir.mkdir(parents=True, exist_ok=True)
        index = kb_dir / "index.json"
        index.write_text(json.dumps({"documents": [dict(d) for d in docs]}, ensure_ascii=False),
                         encoding="utf-8")
        return index

    def _index(self) -> core.KnowledgeIndex:
        return core.KnowledgeIndex(core.Runtime(self.root))

    def test_search_finds_a_table_published_by_the_knowledge_plugin(self) -> None:
        self._publish([PUBLISHED_DOC])
        hits = self._index().search("dwd_order_rt")
        self.assertTrue(hits, "按表名搜索应当命中知识库插件发布的文档")
        self.assertEqual(hits[0]["uri"], PUBLISHED_DOC["uri"])
        self.assertEqual(hits[0]["tables"], ["dwd_order_rt"])

    def test_read_returns_the_abstract_for_a_published_uri(self) -> None:
        self._publish([PUBLISHED_DOC])
        self.assertEqual(self._index().read(PUBLISHED_DOC["uri"]), PUBLISHED_DOC["abstract"])

    def test_read_rejects_a_uri_outside_the_prefix(self) -> None:
        """知识源铁律：不在 uri_prefix 下的知识源一律拒绝。"""
        self._publish([PUBLISHED_DOC])
        index = self._index()
        for bad in ("file:///etc/passwd", "viking://resources-evil/x.md", "domains/order/tables/x.md"):
            with self.assertRaises(core.RtError, msg=bad):
                index.read(bad)

    def test_every_published_field_the_consumer_reads_is_present(self) -> None:
        """消费侧真正读的字段：uri / domain / layer / tables / abstract。

        改了生产端的字段名，这条会红——它是两侧 schema 的对齐点。
        """
        self._publish([PUBLISHED_DOC])
        hits = self._index().search("order")
        self.assertTrue(hits)
        for key in core.KB_DOCUMENT_FIELDS:
            self.assertIn(key, hits[0], f"消费侧要读 {key}，生产侧必须写")

    def test_falls_back_to_the_offline_plugin_index_when_own_dir_is_empty(self) -> None:
        """生产端目前只写离线插件的 .data-dev；本插件自己那份优先，找不到就退到那边。"""
        self._publish([PUBLISHED_DOC], where=".data-dev")
        index = self._index()
        self.assertEqual(index.path, self.root / ".data-dev" / "mock" / "kb" / "index.json")
        self.assertEqual(index.search("dwd_order_rt")[0]["uri"], PUBLISHED_DOC["uri"])

    def test_own_index_wins_over_the_offline_one(self) -> None:
        self._publish([PUBLISHED_DOC], where=".data-dev")
        mine = dict(PUBLISHED_DOC, uri="viking://resources/domains/order/tables/rt_mine.md",
                    tables=["rt_mine"])
        self._publish([mine], where=".rtd")
        index = self._index()
        self.assertEqual(index.path, self.root / ".rtd" / "mock" / "kb" / "index.json")
        self.assertEqual(index.search("rt_mine")[0]["uri"], mine["uri"])

    def test_configured_index_path_overrides_both_candidates(self) -> None:
        elsewhere = self._publish([PUBLISHED_DOC], where="elsewhere")
        (self.root / ".rtd" / "config.json").write_text(
            json.dumps({"knowledge": {"index_path": str(elsewhere)}}, ensure_ascii=False),
            encoding="utf-8")
        self.assertEqual(self._index().path, elsewhere)

    def test_missing_index_is_reported_not_invented(self) -> None:
        """没有索引就如实说没有：search 返回空、status 标不存在，不编内容。"""
        index = self._index()
        state = index.status()
        self.assertFalse(state["index_exists"])
        self.assertEqual(state["document_count"], 0)
        self.assertEqual(index.search("随便什么"), [])
        self.assertEqual(index.read(PUBLISHED_DOC["uri"]), "")


if __name__ == "__main__":
    unittest.main()
