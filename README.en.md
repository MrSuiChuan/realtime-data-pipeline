# realtime-data-plugin

Turns realtime data-task development into a **state machine with hard gates**. The agent works inside a phase,
but a phase only exits when machine-checkable evidence says so.

[![ci](https://github.com/MrSuiChuan/realtime-data-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/MrSuiChuan/realtime-data-pipeline/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)

Install it into Codex or Claude Code and it drives your local Flink, Kafka, lakehouse and metadata platform
to take one realtime task from requirement to production, leaving machine-checkable evidence at every step.
It does not decide your semantics and it does not touch production state for you, it makes both traceable.

Chinese documentation is the primary one and much more complete, see [README.md](./README.md).

## The problem it solves

Realtime task development rarely fails because someone cannot write SQL. It fails in three places.

1. **Unreliable evidence** — compile looked fine, publish probably succeeded, and then the table is empty.
2. **Leaking confirmation** — one yes is treated as blanket approval for start, backfill or offline actions.
3. **Lost state** — a new session does not know which object, version or trace ID was in flight, and
   re-issuing a write is an incident.

The plugin makes all three mechanical. Phases have gates, gates are written only by the engine from evidence,
evidence is hashed on disk, and resuming starts by reading the real state back.

## What it is good for

| Scenario | What it keeps an eye on |
| --- | --- |
| Building a realtime task from scratch (messaging to compute to lake or warehouse) | Semantics written as checkable assertions, reference tables readable, compile reaching a terminal success, results matching an independent baseline |
| Migrating an existing task to a new engine or platform | Whether the source task really stopped, a recovery point given by the user (it refuses to auto-fill the current time), read-back equality before and after |
| Inspecting and diagnosing production tasks | Read-only interfaces only, inspection never mutates state, mutation goes through a separate path with confirmation |
| Tuning and lifecycle actions (hot update, offline, backfill, cancel) | Current-turn confirmation for high-risk actions and a platform trace ID at the end, recorded honestly as failure when absent |
| Handing work across sessions or people | Evidence ledger, execution records and cross-session reconciliation that stops on any mismatch |
| No platform at all, only open-source components | The open-source path: a 13-component registry plus a local lab with recipes for start, stop, readiness and smoke |

## The workflow

```
discover → design → build → debug → configure → submit → publish → start
```

Each phase owns gates, and gates have exactly two sources, which can never substitute for each other.

| Phase | Gate | Kind | Passing condition |
| --- | --- | --- | --- |
| design | `refs_published` | read-back | Every referenced table reads back as published |
| build | `compile_ok` | read-back | Compile receipt in a terminal success state |
| debug | `debug_confirmed` | confirmation | The user's own words for this turn |
| configure | `sla_decided` | confirmation | An explicit decision, skipping counts but still needs the words |
| submit | `submit_ok` | read-back | Submit receipt |
| publish | `publish_ok` | read-back | Publish receipt plus object read-back |
| start | `start_confirmed` | confirmation | Confirmation for a high-risk action |
| start (migration) | `source_stopped` / `reset_time` | confirmation | Source stopped, plus a recovery point given by the user |

Four evidence kinds are accepted, all stored as hashed JSON: `refs_readback`, `compile_receipt`,
`submit_receipt`, `publish_receipt`. A failed query must never be recorded as no data,
which is why a failure is `published: null` with a reason, never `published: false`.

## Install

```bash
# Codex
codex plugin marketplace add <path-to-this-repo>
codex plugin add realtime-data-plugin@personal

# Claude Code (ships .claude-plugin/marketplace.json)
claude plugin marketplace add <path-to-this-repo>
claude plugin install realtime-data-plugin@realtime-data-plugin
```

**Open a new session after installing.** The host asks whether you trust the plugin's hooks, say yes,
otherwise the hard gates are not enforced. See `docs/host-hooks.md` for how to verify that they are live.

## Engine CLI

The engine lives at `.rtd/engine/rtd.py` and is copied into your project by `setup`, so it travels with the project.

| Command | What it does |
| --- | --- |
| `setup` | Create the runtime, copy the engine in, write the config template |
| `status` | Current phase, gate gaps, and the next command to run |
| `object set` | Register the working object (file id, name, version, instance) |
| `evidence add` | Register and validate a structured receipt, returns an evidence id |
| `gate set` | Set a gate from `--evidence <id>` or `--user-confirm "<quote>"` |
| `advance` | Move phase, back-jumps and skips need `--allow-back --reason` |
| `run start` / `run finish` | Execution records, high-risk runs need `--trace` |
| `env check` | Executor health for both paths |
| `knowledge status` / `search` / `read` | Read-only access to the knowledge index written by the knowledge-base plugin |
| `resume` | Cross-session reconciliation |
| `verify` | Final self-check of state, evidence hashes and gate references |

## Executors: two paths

Real command names, MCP service names, addresses and limits all come from the project-level `.rtd/config.json`.
The repository contains no platform-specific names. When configuration is incomplete the engine reports the gap
and stops, it never guesses a command name, never installs anything and never silently switches paths.

Open-source path: `governance/oss-components.json` registers 13 realtime components across compute, messaging,
lakehouse tables, stream storage, serving and CDC, and every one of them has been run locally with readings
recorded in `docs/oss-component-ledger.md`. `tools/oss_cli.py` wraps Flink and Fluss
(`jobs`, `status`, `cancel`, `submit`, `query`, `evidence refs`), and `tools/oss_lab.py` manages the local lab
(`list`, `plan`, `status`, `start`, `stop`, `smoke`, `install`).

Platform path: a platform CLI plus domain MCP servers. Real-environment verification for this path is
**not done yet** and is presented as unverified.

## Real case

The whole thing was exercised end to end on a real chain, real order details into Kafka, a streaming Flink job
writing Paimon ODS, DWD and ADS layers, producing realtime top-3 products by sales amount, cross-checked
against an independent computation on the source database with the three rows matching exactly.

What the process caught on the way is recorded in `docs/optimization-real-case-2026-10.md`,
including duplicate delivery inflating an aggregation built directly on an append stream by roughly 27 percent
while row counts still looked perfectly normal.

## Requirements

Python 3.11+, standard library only for the engine, validators and tools, pytest for the test suite.
Windows, macOS and Linux all work, and `tools/adapt_hooks.py` adapts the hook launcher to your platform.

## License

Apache License 2.0, see `LICENSE` and `NOTICE`. Third-party names and trademarks are scoped in
`docs/third-party-dependencies.md`. This repository ships no third-party binaries.
