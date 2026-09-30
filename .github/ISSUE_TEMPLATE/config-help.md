---
name: 配置求助
about: 接不上自己的平台 / 组件，需要帮看配置
labels: [question]
---

## 你走的是哪条路

- [ ] 平台路径（平台 CLI + 各域 MCP）
- [ ] 开源路径（Flink / Kafka / Spark / 湖表 / ClickHouse / CDC …）

## 跑 env check 的输出

```bash
py -3 .rtd/engine/rtd.py env check --project .
```

```
# 把输出贴在这里（它会说明"缺哪一项"，通常直接给出答案）
```

## 你的配置**形状**（不要贴真实值）

<!-- 只写有哪些键、有没有填，例如：executors.oss_flink.home 已填、rest_endpoint 未填 -->

## 已经试过什么

<!-- 包括失败的尝试。失败的现场比成功的结论更有用 -->
