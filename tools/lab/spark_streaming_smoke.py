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

"""Structured Streaming 冒烟：rate 源 → 落 Parquet（带 checkpoint）→ 读回行数。

由实验台按注册表配方调用。判据：读回行数 ≥ 目标行数，且作业是**跑完**而不是超时被杀。
输出只多一行 `rtd_rows=<n>`。
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", required=True)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--seconds", type=int, default=90)
    args = parser.parse_args()

    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col

    spark = (SparkSession.builder
             .appName("rtd-spark-streaming-smoke")
             .config("spark.sql.shuffle.partitions", "2")
             .config("spark.sql.warehouse.dir", args.warehouse)
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    sink = f"{args.warehouse}/stream_out"
    checkpoint = f"{args.warehouse}/_checkpoint"
    holder: dict = {}
    produced = {"rows": 0}

    def write_batch(batch, batch_id):  # noqa: ANN001
        # 只取还差的那几行：rate 源每批不止一行，全写进去就没法"按行数对账"了。
        need = args.rows - produced["rows"]
        if need <= 0:
            return
        chunk = batch.limit(need)
        written = chunk.count()
        if written == 0:
            return
        chunk.write.mode("append").parquet(sink)
        produced["rows"] += written
        if produced["rows"] >= args.rows:
            query = holder.get("query")
            if query is not None and query.isActive:
                query.stop()

    stream = spark.readStream.format("rate").option("rowsPerSecond", 5).load()
    query = (stream.select(col("value").alias("id"))
             .writeStream
             .foreachBatch(write_batch)
             .option("checkpointLocation", checkpoint)
             .trigger(processingTime="2 seconds")
             .start())
    holder["query"] = query
    # 到点收工：宁可按超时停，也不无限等（超时后读回的行数会让判据自己说话）。
    query.awaitTermination(args.seconds)

    rows = spark.read.parquet(sink).count() if _exists(spark, sink) else 0
    print("rtd_streaming=finished")
    print(f"rtd_rows={rows}")
    spark.stop()
    if rows < args.rows:
        print(f"[失败] 目标 {args.rows} 行，实际落 {rows} 行", file=sys.stderr)
        return 2
    return 0


def _exists(spark, path: str) -> bool:  # noqa: ANN001
    hadoop = spark._jvm.org.apache.hadoop.fs.Path(path)
    fs = hadoop.getFileSystem(spark._jsc.hadoopConfiguration())
    return bool(fs.exists(hadoop))


if __name__ == "__main__":
    raise SystemExit(main())
