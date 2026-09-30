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

# Debezium CDC 冒烟：本地 Postgres 写入 → Kafka Connect 上的 Debezium → Kafka topic → 读回事件数。
#
# 为什么是一段脚本而不是几条配方步骤：CDC 这条链路**天然是多组件的**——
# 源库、Kafka broker、Connect worker、连接器四样都要在位，顺序也不能颠倒。
# 把它拆成注册表里的一串 `start` 步骤，读的人看不出"先决条件是什么"。
#
# 用法（实验台按注册表的 smoke 步骤调用）：
#   debezium_cdc_smoke.sh --kafka-home <dir> --connect-url <url> --plugin-dir <dir> \
#       --pg-port <port> --pg-data <dir> --rows <n> --topic <name> --work-dir <dir>
#
# 判据：Kafka topic 里读到的 CDC 事件条数 ≥ 写入行数。读不到就是失败，不写成"暂无数据"。
set -uo pipefail

KAFKA_HOME=""; CONNECT_URL=""; PLUGIN_DIR=""; PG_PORT="5433"; PG_DATA=""; ROWS=3
TOPIC="rtd_cdc_smoke"; WORK_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --kafka-home) KAFKA_HOME=$2; shift 2;;
    --connect-url) CONNECT_URL=$2; shift 2;;
    --plugin-dir) PLUGIN_DIR=$2; shift 2;;
    --pg-port) PG_PORT=$2; shift 2;;
    --pg-data) PG_DATA=$2; shift 2;;
    --rows) ROWS=$2; shift 2;;
    --topic) TOPIC=$2; shift 2;;
    --work-dir) WORK_DIR=$2; shift 2;;
    *) echo "未知参数：$1" >&2; exit 64;;
  esac
done

PGBIN=$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | tail -1)
[ -n "$PGBIN" ] || { echo "[失败] 找不到本地 Postgres 二进制" >&2; exit 3; }
mkdir -p "$WORK_DIR" "$PG_DATA"

wait_port() {  # wait_port host port 秒数
  local h=$1 p=$2 limit=$3 i=0
  while [ $i -lt "$limit" ]; do
    (exec 3<>"/dev/tcp/$h/$p") 2>/dev/null && return 0
    sleep 2; i=$((i + 2))
  done
  return 1
}

# ── 1. Kafka broker：CDC 的落点。没起就在这里起，不假设别的会话还活着 ──────
# （实测 WSL 的空闲回收会把之前会话起的进程带走，所以这条链路必须自己把先决条件拉起来。）
if ! wait_port 127.0.0.1 9092 1; then
  mkdir -p "$KAFKA_HOME/lab-data" "$KAFKA_HOME/logs"
  if [ ! -s "$KAFKA_HOME/lab-server.properties" ]; then
    sed "s|^log.dirs=.*|log.dirs=$KAFKA_HOME/lab-data|" \
      "$KAFKA_HOME/config/server.properties" > "$KAFKA_HOME/lab-server.properties"
  fi
  if [ ! -s "$KAFKA_HOME/lab-data/meta.properties" ]; then
    "$KAFKA_HOME/bin/kafka-storage.sh" format \
      -t "$("$KAFKA_HOME/bin/kafka-storage.sh" random-uuid)" \
      -c "$KAFKA_HOME/lab-server.properties" --standalone > "$WORK_DIR/kafka-format.log" 2>&1
  fi
  setsid nohup "$KAFKA_HOME/bin/kafka-server-start.sh" "$KAFKA_HOME/lab-server.properties" \
    > "$KAFKA_HOME/logs/server.out" 2>&1 < /dev/null &
  sleep 10
  wait_port 127.0.0.1 9092 90 \
    || { echo "[失败] Kafka 起不来，见 $KAFKA_HOME/logs/server.out" >&2; exit 3; }
fi

# ── 2. 源库：一个只属于实验的 Postgres（开逻辑复制）────────────────────────
if [ ! -s "$PG_DATA/PG_VERSION" ]; then
  "$PGBIN/initdb" -D "$PG_DATA" -U "$(whoami)" --auth=trust > "$WORK_DIR/initdb.log" 2>&1 \
    || { echo "[失败] initdb 见 $WORK_DIR/initdb.log" >&2; exit 3; }
fi
if [ -s "$PG_DATA/postmaster.pid" ] && wait_port 127.0.0.1 "$PG_PORT" 1; then
  echo "源库已在跑（端口 $PG_PORT）"
else
  "$PGBIN/pg_ctl" -D "$PG_DATA" -l "$WORK_DIR/pg.log" \
    -o "-p $PG_PORT -c wal_level=logical -c max_replication_slots=4 -c max_wal_senders=4 -c listen_addresses=127.0.0.1 -c unix_socket_directories=$WORK_DIR" \
    start > "$WORK_DIR/pgctl.log" 2>&1 || { echo "[失败] 源库起不来，见 $WORK_DIR/pg.log" >&2; exit 3; }
  wait_port 127.0.0.1 "$PG_PORT" 60 || { echo "[失败] 源库端口不通，见 $WORK_DIR/pg.log" >&2; exit 3; }
fi

export PGPASSWORD=
PSQL="$PGBIN/psql -h 127.0.0.1 -p $PG_PORT -U $(whoami) -d postgres -v ON_ERROR_STOP=1 -q"
$PSQL -c "SELECT 1 FROM pg_database WHERE datname='rtd_lab'" | grep -q 1 \
  || $PSQL -c "CREATE DATABASE rtd_lab" > "$WORK_DIR/createdb.log" 2>&1
PSQL_DB=$($PSQL -c "SELECT 1" >/dev/null 2>&1 && echo "$PGBIN/psql -h 127.0.0.1 -p $PG_PORT -U $(whoami) -d rtd_lab -v ON_ERROR_STOP=1 -q")
$PSQL_DB -c "DROP TABLE IF EXISTS public.t_orders" >/dev/null 2>&1
$PSQL_DB -c "CREATE TABLE public.t_orders (id INT PRIMARY KEY, amount NUMERIC)" >/dev/null

# ── 3. Connect worker：Debezium 连接器跑在它上面 ──────────────────────────
if ! curl -sf -m 5 "$CONNECT_URL/connectors" >/dev/null 2>&1; then
  cat > "$WORK_DIR/connect-worker.properties" <<EOF
bootstrap.servers=127.0.0.1:9092
key.converter=org.apache.kafka.connect.json.JsonConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
offset.storage.file.filename=$WORK_DIR/connect.offsets
offset.flush.interval.ms=1000
# plugin.path 要给**父目录**：Connect 把该目录下的每个子目录当成一个插件（一个类加载器）。
# 直接指到装 jar 的目录，它会逐个 jar 建类加载器，连接器就找不到同目录的 debezium-core。
plugin.path=$(dirname "$PLUGIN_DIR")
listeners=http://127.0.0.1:8083
EOF
  cat > "$WORK_DIR/connect-connector.properties" <<EOF
name=rtd-pg-connector
connector.class=io.debezium.connector.postgresql.PostgresConnector
tasks.max=1
plugin.name=pgoutput
database.hostname=127.0.0.1
database.port=$PG_PORT
database.user=$(whoami)
database.dbname=rtd_lab
topic.prefix=rtdlab
table.include.list=public.t_orders
EOF
  setsid nohup "$KAFKA_HOME/bin/connect-standalone.sh" \
    "$WORK_DIR/connect-worker.properties" "$WORK_DIR/connect-connector.properties" \
    > "$WORK_DIR/connect.out" 2>&1 < /dev/null &
  # 插件扫描要花几秒，别用固定 sleep 赌它：一直等到 REST 起来或超时。
  i=0
  while [ $i -lt 60 ]; do
    curl -sf -m 5 "$CONNECT_URL/connectors" >/dev/null 2>&1 && break
    sleep 2; i=$((i + 2))
  done
  curl -sf -m 10 "$CONNECT_URL/connectors" >/dev/null 2>&1 \
    || { echo "[失败] Connect worker 起不来，见 $WORK_DIR/connect.out" >&2; exit 3; }
fi

# ── 4. 真写：向源库插 N 行 ───────────────────────────────────────────────
$PSQL_DB -c "INSERT INTO public.t_orders SELECT g, g * 10 FROM generate_series(1, $ROWS) AS g" >/dev/null

# ── 5. 真读：从 Kafka 的 CDC topic 读回事件 ──────────────────────────────
TOPIC_NAME="rtdlab.public.t_orders"
for _ in 1 2 3 4 5 6; do
  "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server 127.0.0.1:9092 \
    --create --if-not-exists --topic "$TOPIC_NAME" --partitions 1 --replication-factor 1 >/dev/null 2>&1
  "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server 127.0.0.1:9092 --list 2>/dev/null | grep -qx "$TOPIC_NAME" && break
  sleep 5
done

raw=$("$KAFKA_HOME/bin/kafka-console-consumer.sh" --bootstrap-server 127.0.0.1:9092 \
  --topic "$TOPIC_NAME" --from-beginning --max-messages "$ROWS" --timeout-ms 30000 2>"$WORK_DIR/consumer.err")
events=$(printf '%s\n' "$raw" | grep -c '"op"')
printf '%s\n' "$raw" > "$WORK_DIR/cdc-events.jsonl"
echo "rtd_cdc_topic=$TOPIC_NAME"
echo "rtd_rows=$events"
[ "$events" -ge "$ROWS" ] || { echo "[失败] 源库写 $ROWS 行，CDC 事件只读到 $events 条" >&2; exit 2; }
exit 0
