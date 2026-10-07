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
FE_ENV=""; BE_ENV=""; HOST_NET=0; ENTRYPOINT_MANAGED=0; BE_ADDR=""; FE_CMD=""; BE_CMD=""
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
    --fe-env) FE_ENV=$2; shift 2;;
    --be-env) BE_ENV=$2; shift 2;;
    --host-network) HOST_NET=1; shift;;
    # 有些镜像的入口脚本自己就把服务起起来了（Doris 就是），这时不能再 exec 一遍启动脚本。
    --entrypoint-managed) ENTRYPOINT_MANAGED=1; shift;;
    # host 网络下拿不到 BE 的容器 IP，直接给它在宿主机上的地址（通常是 127.0.0.1）。
    --be-address) BE_ADDR=$2; shift 2;;
    # 需要先改镜像里的配置再启动时用（例如把 Doris FE 默认的 8GB 堆降下来）。
    --fe-cmd) FE_CMD=$2; shift 2;;
    --be-cmd) BE_CMD=$2; shift 2;;
    *) echo "未知参数：$1" >&2; exit 64;;
  esac
done
[ -n "$ACTION" ] || { echo "用法：serving_cluster_up.sh up|down ..." >&2; exit 64; }

FE="$PREFIX-fe"; BE="$PREFIX-be"
wait_port() { local h=$1 p=$2 lim=$3 i=0; while [ $i -lt "$lim" ]; do (exec 3<>"/dev/tcp/$h/$p") 2>/dev/null && return 0; sleep 3; i=$((i + 3)); done; return 1; }
env_flags() { local spec=$1 out=""; local IFS=','; for kv in $spec; do [ -n "$kv" ] && out="$out -e $kv"; done; echo "$out"; }

if [ "$ACTION" = "down" ]; then
  docker rm -f "$FE" "$BE" >/dev/null 2>&1
  echo "已停 $FE 与 $BE"
  exit 0
fi

[ -n "$FE_IMG" ] && [ -n "$BE_IMG" ] || { echo "[失败] 需要 --fe-image 与 --be-image" >&2; exit 64; }

if [ "$HOST_NET" = "1" ]; then NET_OPTS="--network host"; PORT_OPTS=""; else
  docker network create "$NET" >/dev/null 2>&1 || true
  NET_OPTS="--network $NET"; PORT_OPTS="-p $MYSQL_PORT:$MYSQL_PORT -p 8030:8030"
fi
docker rm -f "$FE" "$BE" >/dev/null 2>&1 || true

# 镜像的默认 CMD 是 /bin/bash，不加 -it 容器会立刻退出（实测踩过）。
# shellcheck disable=SC2086
if [ -n "$FE_CMD" ]; then
  docker run -itd --name "$FE" $NET_OPTS $PORT_OPTS $(env_flags "$FE_ENV") \
    --entrypoint bash "$FE_IMG" -lc "$FE_CMD" >/dev/null
else
  docker run -itd --name "$FE" $NET_OPTS $PORT_OPTS $(env_flags "$FE_ENV") "$FE_IMG" >/dev/null
fi || { echo "[失败] FE 容器起不来" >&2; exit 3; }
if [ "$ENTRYPOINT_MANAGED" = "0" ]; then
  docker exec "$FE" bash -lc "$FE_HOME/bin/start_fe.sh --daemon" >/dev/null 2>&1
fi
# Doris 的 FE 首次启动要建元数据，实测比 StarRocks 慢，给足 5 分钟。
if ! wait_port 127.0.0.1 "$MYSQL_PORT" 300; then
  echo "[失败] FE 的查询端口 $MYSQL_PORT 没起来" >&2
  docker exec "$FE" bash -lc "tail -15 $FE_HOME/log/fe.log" 2>&1 | tail -15
  exit 3
fi

# shellcheck disable=SC2086
if [ -n "$BE_CMD" ]; then
  docker run -itd --name "$BE" $NET_OPTS -p 8040:8040 $(env_flags "$BE_ENV") \
    --entrypoint bash "$BE_IMG" -lc "$BE_CMD" >/dev/null
else
  docker run -itd --name "$BE" $NET_OPTS -p 8040:8040 $(env_flags "$BE_ENV") "$BE_IMG" >/dev/null
fi || { echo "[失败] BE 容器起不来" >&2; exit 3; }
BE_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$BE")
if [ "$ENTRYPOINT_MANAGED" = "0" ]; then
  [ -n "$BE_IP" ] || { echo "[失败] 拿不到 BE 的容器 IP" >&2; exit 3; }
  # BE 必须知道用哪个网卡对外：容器里既有 lo 又有 eth0，不指定会注册成错地址。
  docker exec "$BE" bash -lc "echo 'priority_networks = ${BE_IP%.*}.0/24' >> $BE_HOME/conf/be.conf"
  docker exec "$BE" bash -lc "$BE_HOME/bin/start_be.sh --daemon" >/dev/null 2>&1
fi

REGISTER_HOST="$BE_IP"
[ -n "$REGISTER_HOST" ] || REGISTER_HOST="$BE_ADDR"
if [ -n "$REGISTER_HOST" ]; then
  mysql -h 127.0.0.1 -P "$MYSQL_PORT" -uroot \
    -e "ALTER SYSTEM ADD BACKEND '$REGISTER_HOST:9050';" >/dev/null 2>&1
fi

# 等心跳：Alive=true 才算真的可用，端口通不算。Doris 的 BE 首次心跳实测要十几秒到一两分钟。
i=0
while [ $i -lt 300 ]; do
  alive=$(mysql -h 127.0.0.1 -P "$MYSQL_PORT" -uroot -N -B \
    -e "SHOW BACKENDS" 2>/dev/null | awk -F'\t' '{print $9}' | head -1)
  [ "$alive" = "true" ] && { echo "rtd_backend_alive=true"; exit 0; }
  sleep 5; i=$((i + 5))
done
echo "[失败] BE 注册后没等到心跳（Alive 不为 true）" >&2
mysql -h 127.0.0.1 -P "$MYSQL_PORT" -uroot -e "SHOW BACKENDS" 2>&1 | tail -3
exit 3
