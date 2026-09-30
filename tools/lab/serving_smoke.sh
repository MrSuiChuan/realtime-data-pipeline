#!/usr/bin/env bash
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
#
# 服务层冒烟（StarRocks 与 Doris 共用）：建库建表 → 写 N 行 → 读回行数。
# 两家都用 MySQL 协议与同一套建表语法（分布键 + 分桶 + 副本数），所以一份就够。
# 判据：读回行数与写入行数一致。只多打印一行 rtd_rows=<n> 供实验台按数据行过滤。
#
# 用法：
#   serving_smoke.sh --host <fe 主机> --port <fe mysql 端口> --user <用户> --rows <n>
set -uo pipefail

HOST=127.0.0.1; PORT=9030; USER=root; ROWS=5
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST=$2; shift 2;;
    --port) PORT=$2; shift 2;;
    --user) USER=$2; shift 2;;
    --rows) ROWS=$2; shift 2;;
    *) echo "未知参数：$1" >&2; exit 64;;
  esac
done

command -v mysql >/dev/null || { echo "[失败] 本机没有 mysql 客户端" >&2; exit 3; }

# 造出 VALUES 列表。注意 seq 的 -f 只允许一个数值转换，所以这里用循环拼。
VALUES=""; i=1
while [ "$i" -le "$ROWS" ]; do
  [ -z "$VALUES" ] || VALUES="${VALUES},"
  VALUES="${VALUES}(${i},'n${i}')"
  i=$((i + 1))
done
SQL="CREATE DATABASE IF NOT EXISTS rtd_lab;
DROP TABLE IF EXISTS rtd_lab.t_roundtrip;
CREATE TABLE rtd_lab.t_roundtrip (id INT, name VARCHAR(32))
  DUPLICATE KEY(id) DISTRIBUTED BY HASH(id) BUCKETS 1
  PROPERTIES ('replication_num' = '1');
INSERT INTO rtd_lab.t_roundtrip VALUES $VALUES;
SELECT COUNT(*) FROM rtd_lab.t_roundtrip;"

raw=$(mysql -h "$HOST" -P "$PORT" -u "$USER" -N -B -e "$SQL" 2>&1)
rc=$?
printf '%s\n' "$raw" > "${TMPDIR:-/tmp}/rtd-starrocks-smoke.log"
if [ $rc -ne 0 ]; then
  echo "[失败] SQL 没跑完：$(printf '%s' "$raw" | tail -2)" >&2
  exit 2
fi

rows=$(printf '%s\n' "$raw" | grep -E '^[0-9]+$' | tail -1)
echo "rtd_rows=${rows:-0}"
[ "${rows:-0}" = "$ROWS" ] || { echo "[失败] 写 $ROWS 行、读回 ${rows:-0} 行" >&2; exit 2; }
exit 0
