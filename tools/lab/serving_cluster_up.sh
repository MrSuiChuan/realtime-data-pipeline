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
# 服务层集群起停（StarRocks 与 Doris 共用）：FE + BE 两个容器，BE 注册进 FE。
#
# 两家是同一个架构血统，容器布局几乎一致，差别只在安装路径与镜像——
# 所以写成一份，用参数区分，而不是抄两份改改路径。
#
# 为什么是脚本而不是注册表里的一串步骤：这段编排有固定的先后关系
# （先起 FE、等它接连接，再起 BE、拿到 BE 的容器 IP、注册、等心跳），
# 拆成步骤列表读的人看不出顺序。命令行参数用 --key value 显式传，不靠位置。
#
# 用法：serving_cluster_up.sh up|down --fe-image <img> --be-image <img> --prefix <name> \
#          [--network <net>] [--mysql-port <p>] [--fe-home <容器内 FE 目录>] [--be-home <容器内 BE 目录>]
set -uo pipefail

ACTION=""; FE_IMG=""; BE_IMG=""; PREFIX=rtd-sr; NET=rtd-sr-net; MYSQL_PORT=9030
FE_HOME=/opt/starrocks/fe; BE_HOME=/opt/starrocks/be
while [ $# -gt 0 ]; do
  case "$1" in
    up|down) ACTION=$1; shift;;
    --fe-image) FE_IMG=$2; shift 2;;
    --be-image) BE_IMG=$2; shift 2;;
    --prefix) PREFIX=$2; shift 2;;
    --network) NET=$2; shift 2;;
    --mysql-port) MYSQL_PORT=$2; shift 2;;
    --fe-home) FE_HOME=$2; shift 2;;
    --be-home) BE_HOME=$2; shift 2;;
    *) echo "未知参数：$1" >&2; exit 64;;
  esac
done
[ -n "$ACTION" ] || { echo "用法：serving_cluster_up.sh up|down ..." >&2; exit 64; }

FE="$PREFIX-fe"; BE="$PREFIX-be"
wait_port() { local h=$1 p=$2 lim=$3 i=0; while [ $i -lt "$lim" ]; do (exec 3<>"/dev/tcp/$h/$p") 2>/dev/null && return 0; sleep 3; i=$((i + 3)); done; return 1; }

if [ "$ACTION" = "down" ]; then
  docker rm -f "$FE" "$BE" >/dev/null 2>&1
  echo "已停 $FE 与 $BE"
  exit 0
fi

[ -n "$FE_IMG" ] && [ -n "$BE_IMG" ] || { echo "[失败] 需要 --fe-image 与 --be-image" >&2; exit 64; }

docker network create "$NET" >/dev/null 2>&1 || true
docker rm -f "$FE" "$BE" >/dev/null 2>&1 || true

# 镜像的默认 CMD 是 /bin/bash，不加 -it 容器会立刻退出（实测踩过）。
docker run -itd --name "$FE" --network "$NET" -p "$MYSQL_PORT:$MYSQL_PORT" -p 8030:8030 "$FE_IMG" >/dev/null \
  || { echo "[失败] FE 容器起不来" >&2; exit 3; }
docker exec "$FE" bash -lc "$FE_HOME/bin/start_fe.sh --daemon" >/dev/null 2>&1
if ! wait_port 127.0.0.1 "$MYSQL_PORT" 120; then
  echo "[失败] FE 的查询端口 $MYSQL_PORT 没起来" >&2
  docker exec "$FE" bash -lc "tail -15 $FE_HOME/log/fe.log" 2>&1 | tail -15
  exit 3
fi

docker run -itd --name "$BE" --network "$NET" -p 8040:8040 "$BE_IMG" >/dev/null \
  || { echo "[失败] BE 容器起不来" >&2; exit 3; }
BE_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$BE")
[ -n "$BE_IP" ] || { echo "[失败] 拿不到 BE 的容器 IP" >&2; exit 3; }
# BE 必须知道用哪个网卡对外：容器里既有 lo 又有 eth0，不指定会注册成错地址。
docker exec "$BE" bash -lc "echo 'priority_networks = ${BE_IP%.*}.0/24' >> $BE_HOME/conf/be.conf"
docker exec "$BE" bash -lc "$BE_HOME/bin/start_be.sh --daemon" >/dev/null 2>&1

mysql -h 127.0.0.1 -P "$MYSQL_PORT" -uroot \
  -e "ALTER SYSTEM ADD BACKEND '$BE_IP:9050';" >/dev/null 2>&1

# 等心跳：Alive=true 才算真的可用，端口通不算。
i=0
while [ $i -lt 120 ]; do
  alive=$(mysql -h 127.0.0.1 -P "$MYSQL_PORT" -uroot -N -B \
    -e "SHOW BACKENDS" 2>/dev/null | awk -F'\t' '{print $9}' | head -1)
  [ "$alive" = "true" ] && { echo "rtd_backend_alive=true"; exit 0; }
  sleep 5; i=$((i + 5))
done
echo "[失败] BE 注册后没等到心跳（Alive 不为 true）" >&2
mysql -h 127.0.0.1 -P "$MYSQL_PORT" -uroot -e "SHOW BACKENDS" 2>&1 | tail -3
exit 3
