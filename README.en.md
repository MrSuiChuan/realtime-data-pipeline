# realtime-data-plugin

Turns realtime data-task development into a **state machine with hard gates**: the agent does the work
inside a phase, but a phase only exits when machine-checkable evidence says so.

中文说明见 [README.md](./README.md)（更完整，包括实验记录与踩坑）。

## The problem it solves

Realtime task development usually fails in three places, and none of them is "can you write SQL":

1. **Unreliable evidence** — "compile looked fine", "publish probably succeeded", and then the table is empty in production.
2. **Confirmation that leaks** — one "yes" is treated as a blanket approval for start / backfill / offline operations.
3. **Lost state** — a new session has no idea which object, version or trace ID was in flight, and re-issuing a write is an incident.

This plugin makes all three mechanical: phases have gates, gates are written only by the engine from evidence,
evidence is hashed on disk, and resuming starts by reading the real state back.

## Three layers

| Layer | Where | What it is |
| --- | --- | --- |
| Governance | `governance/` | Safety constitution (gates, read-only boundary), executor arbitration, capability matrix, component registry |
| Workflow | `workflows/`, `commands/` | Runbooks and the command entry points; `skills/` is generated from `commands/` |
| Executors | `executors/` + project-level `.rtd/config.json` | Contracts only. Real command names, addresses and limits live in your project, never in this repo |

## Install

Both hosts share the same engine, workflows and hook scripts.

```bash
# Codex
codex plugin marketplace add <path-to-this-repo>
codex plugin add realtime-data-plugin@personal

# Claude Code (ships .claude-plugin/marketplace.json)
claude plugin marketplace add <path-to-this-repo>
claude plugin install realtime-data-plugin@realtime-data-plugin
```

**Open a new session after installing** — the plugin list is read at session start. The host will ask whether
you trust the plugin's hooks; **say yes**, otherwise the hard gates are not enforced.

## Quick start (no platform account needed)

```bash
py -3 <plugin>/engine/rtd.py setup --project .      # creates .rtd/ and copies the engine in
py -3 .rtd/engine/rtd.py evidence add --kind compile_receipt --from compile.json \
    --tool local-demo --command "echo compile ok"
py -3 .rtd/engine/rtd.py status
```

Expected output for each step is captured verbatim in the Chinese [README.md](./README.md#跑一遍应该看到什么不依赖任何平台).
`setup` reports gaps and stops instead of guessing; `evidence add` validates the receipt on the spot and returns an evidence ID.

## Executors: pick one path

* **Platform path** — a platform CLI plus domain MCP servers.
* **Open-source path** — the components registered in `governance/oss-components.json`
  (Flink, Kafka, Spark Structured Streaming, Paimon, Fluss, Iceberg, Hudi, Delta, Pulsar, Debezium, Doris, StarRocks, ClickHouse).

Readiness is judged on the subset you actually configured: whatever you touched must be complete,
components you never touched are not counted as gaps. `rtd-env` reports both paths.

For local experiments there is `tools/oss_lab.py`: it installs, starts, stops, probes and smoke-tests components
**one heavy component at a time**, and it refuses to start a second one. Component knowledge comes from the registry;
machine-specific settings live in `.rtd/lab.json`. Twelve of the thirteen registered components have been
verified end-to-end on a real local cluster; the thirteenth (Doris) is documented with its blockers.

## Scope and boundaries

| Does | Does not |
| --- | --- |
| Phase state machine and gates (evidence vs. per-action confirmation, not interchangeable) | Ship any platform command names or service names — those come from your config |
| Evidence ledger (hash-verifiable), execution records, cross-session reconciliation | Change production for you; every state-changing action needs a fresh confirmation |
| Runbooks and executor contracts | Bundle proprietary schema snapshots or internal test data |
| Open-source stack verified locally (Flink, Paimon, Fluss, Kafka, Spark, Iceberg, Hudi, Delta, ClickHouse, Debezium, Pulsar, StarRocks) | The platform path is **not verified against a real environment**; it is presented as unverified |

## Docs

Most documents are written in Chinese. Start from [docs/README.md](./docs/README.md) (map by role),
then [docs/glossary.md](./docs/glossary.md) if the vocabulary looks unusual — every term there maps to a judgement rule.

| Document | Content |
| --- | --- |
| [GOVERNANCE.md](./GOVERNANCE.md) | Roles, lazy consensus, what needs stronger agreement, dispute escalation |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Where to change what, DCO sign-off, review rules |
| [SECURITY.md](./SECURITY.md) | Supported versions and how to report privately |
| [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 |
| [docs/release-process.md](./docs/release-process.md) | Versioning, packaging checklist, release steps |
| [docs/apache-readiness-audit.md](./docs/apache-readiness-audit.md) | Open-source readiness audit against Apache conventions |
| [docs/oss-component-ledger.md](./docs/oss-component-ledger.md) | Which components are verified, and how far |
| [CHANGELOG.md](./CHANGELOG.md) | What changed, including what is *not* done |

## License and community

Apache License 2.0 — see [LICENSE](./LICENSE) and [NOTICE](./NOTICE).
Third-party names are used only to describe compatibility; see [docs/third-party-dependencies.md](./docs/third-party-dependencies.md).

Bugs and proposals: use the issue templates under `.github/`. Security issues: follow [SECURITY.md](./SECURITY.md),
do not open a public issue.
