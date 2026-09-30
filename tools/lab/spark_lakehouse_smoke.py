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

"""湖表格式冒烟：建命名空间 → 建表 → 写入 N 行 → 批模式读回。

由实验台按注册表配方调用（`tools/oss_lab.py`），不单独对外承诺接口：

    spark-submit <jars/conf 由配方给> spark_lakehouse_smoke.py --format delta --warehouse <目录> --rows 5

判据只有一条：**读回行数与写入行数一致**。建表成功、INSERT 不报错都不算数。
输出只多一行 `rtd_rows=<n>`，让实验台的"数据行长什么样"过滤能精确数行。
"""

from __future__ import annotations

import argparse
import sys


def ddl_for(fmt: str, namespace: str, table: str) -> tuple[list[str], str]:
    """返回（要先执行的语句, 全限定表名）。格式差异只集中在这一处。"""
    columns = "(id INT, name STRING)"
    if fmt == "delta":
        return [f"CREATE DATABASE IF NOT EXISTS {namespace}",
                f"CREATE TABLE IF NOT EXISTS {namespace}.{table} {columns} USING DELTA"], \
               f"{namespace}.{table}"
    if fmt == "iceberg":
        return [f"CREATE NAMESPACE IF NOT EXISTS iceberg.{namespace}",
                f"CREATE TABLE IF NOT EXISTS iceberg.{namespace}.{table} {columns} USING ICEBERG"], \
               f"iceberg.{namespace}.{table}"
    if fmt == "hudi":
        return [f"CREATE DATABASE IF NOT EXISTS {namespace}",
                f"CREATE TABLE IF NOT EXISTS {namespace}.{table} {columns} USING HUDI "
                f"TBLPROPERTIES (type='cow', primaryKey='id', preCombineField='id')"], \
               f"{namespace}.{table}"
    if fmt == "paimon":
        return [f"CREATE DATABASE IF NOT EXISTS {namespace}",
                f"CREATE TABLE IF NOT EXISTS {namespace}.{table} {columns} USING PAIMON "
                f"TBLPROPERTIES ('primary-key'='id')"], \
               f"{namespace}.{table}"
    raise SystemExit(f"不认识的湖表格式：{fmt}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", required=True, choices=["delta", "iceberg", "hudi", "paimon"])
    parser.add_argument("--warehouse", required=True)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--namespace", default="db_rtd")
    parser.add_argument("--table", default="t_roundtrip")
    args = parser.parse_args()

    from pyspark.sql import SparkSession

    spark = (SparkSession.builder
             .appName(f"rtd-lakehouse-smoke-{args.format}")
             .config("spark.sql.shuffle.partitions", "2")
             .config("spark.sql.warehouse.dir", args.warehouse)
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    setup, qualified = ddl_for(args.format, args.namespace, args.table)
    # 先删再建：重跑时行数才是确定的（Hudi 这类不支持按 SQL DELETE 清表）。
    spark.sql(f"DROP TABLE IF EXISTS {qualified}")
    for statement in setup:
        spark.sql(statement)

    spark.sql(f"INSERT INTO {qualified} SELECT id, concat('n', id) FROM range(1, {args.rows + 1})")
    rows = spark.sql(f"SELECT COUNT(*) AS c FROM {qualified}").collect()[0][0]

    print(f"rtd_format={args.format}")
    print(f"rtd_rows={rows}")
    spark.stop()
    if rows != args.rows:
        print(f"[失败] 写 {args.rows} 行、读回 {rows} 行", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
