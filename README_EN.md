# AKDesk Fixed

Turn funding rates, yield curves and CGB futures changes into a concise fixed-income brief with sources and timestamps.

[![MIT](https://img.shields.io/badge/license-MIT-44c8bb.svg)](./LICENSE) [![macOS](https://img.shields.io/badge/platform-macOS-0b1727.svg)](#local-installation) [![v1.1.0](https://img.shields.io/badge/version-v1.1.0-f5b84b.svg)](https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest)

**[Try the browser demo](https://raistlinsha-plus.github.io/akdesk-fixed/)** · **[Download the local app](https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest)** · [中文](./README.md) · [Feedback](https://github.com/raistlinsha-plus/akdesk-fixed/issues/new/choose)

![One-page brief UI with fixed synthetic data](./docs/media/v1.1.0/05-brief.png)

Follow one path: **observe changes → verify the yield curve → add notes and export a brief**.

The static demo uses fixed **2026-08-03 synthetic data**, not live quotes. It needs no installation, login or API key and connects to no market-data service or local backend. The app's business UI is currently Chinese; this README does not imply a fully English-localized product.

[60-second video](https://raistlinsha-plus.github.io/akdesk-fixed/akdesk-demo-60s.mp4) · [Example Markdown](./docs/media/v1.1.0/示例-固收简报.md) · [Reproducible AKShare case](./docs/examples/AKShare-一页固收简报.md)

## Local installation

Targets Apple Silicon MacBook Air, **macOS 12+ and Python 3.11–3.13**. Initial installation needs network access and about 1 GB of free space. The official package includes a prebuilt UI; normal use requires no Node.js, Docker or Rust.

macOS 12+ is a compatibility target. This release was physically tested on macOS 26.6.2 / Apple Silicon; other OS versions have not each been tested in this cycle.

1. Install a supported Python; with Homebrew, use `brew install python@3.13`.
2. Select the `AKDesk-Fixed-v1.1.0.zip` asset in [Releases](https://github.com/raistlinsha-plus/akdesk-fixed/releases/latest), verify its SHA-256 and unzip the whole package.
3. Double-click `start-macos.command`. It runs local checks, installs locked dependencies and opens `http://127.0.0.1:8765`.

GitHub's automatic **Source code** archive is for source inspection and development. It is different from the official ZIP checked for release manifest, built assets and executable permissions; source users may need to build the UI or restore script permissions. Available downloads and verification results are recorded in the Release page and [release/acceptance record](./docs/AKDesk-Fixed-v1.1.0-发布与验收记录.md).

If macOS blocks the launcher, right-click and choose Open. To restore executable permissions:

```bash
chmod +x start-macos.command start-macos-demo.command stop-macos.command
```

Stop with `Control+C` in the original launcher terminal, or double-click `stop-macos.command`. Closing the browser does not stop the service.

The launcher checks Python, release files, directory permissions, disk space and certificate locations, with recovery guidance for installation failures. Run `python3 scripts/preflight.py --json` for an offline check. In the app, “使用与反馈” (Usage and feedback) lets you explicitly generate, preview, copy or download a redacted diagnostic summary. It does not upload automatically or include keys, personal paths, raw errors, databases or research content.

## What is included

- A one-page brief for funding, the 10Y yield, curve spreads and CGB futures, with gaps and per-source timestamps. The full daily review remains available.
- Watchlists, evidence collection, research projects, topics, counter-evidence, tasks and weekly reviews.
- Credit Watch R2, FX, macro charts, sovereign comparisons and external event leads.
- Explicit sample/mixed/unknown provenance, cache status and missing values. Missing inputs do not become zero or a market-direction conclusion.

Temporary notes can accompany the brief's Markdown and print/PDF output but are not automatically saved as research notes. All earlier features remain; see the [v1.1 introduction](./docs/AKDesk-Fixed-v1.1.0-产品介绍.md) and [full feature manual](./docs/AKDesk-Fixed-v1.0.0-用户手册.md), currently in Chinese.

## Data sources and optional services

| Source | Purpose | Setup and boundaries |
| --- | --- | --- |
| AKShare / AKTools ecosystem | China funding, curves, bonds, CGB futures, convertibles, issuance and selected FX | This app currently uses Python AKShare; public-data access layer, not an exchange-authorized live feed |
| FRED official API | US rates, inflation, jobs, growth and release reviews | User-owned key; request-scoped observations, stored research references rather than observation values |
| World Bank API v2 | Cross-country structural comparisons | No key; attribution, same-year alignment, explicit gaps and cache state |
| GDELT DOC 2.0 | External event leads | No key; on-demand metadata only, no article-body collection or automatic credit judgment |

The China-market path needs no FRED or AI key. FRED and AI are optional; users supply their own credentials, managed through macOS Keychain. AI sends trimmed context after user authorization, with usage charged against the user's own provider account.

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.

The app includes no usage-telemetry or tracking SDK. Research stays local, and feedback is submitted by the user.

## Intended use

For individual fixed-income/macro researchers, AKShare/Python users and people evaluating local research workflows. Try the sample output before installing.

Not a sole source for production trading, accounting valuation, regulatory reporting or risk-limit decisions. Upstream availability and timeliness vary; no real-time or institutional SLA is promised. Not investment advice.

## Documentation and feedback

- [v1.1 introduction](./docs/AKDesk-Fixed-v1.1.0-产品介绍.md) · [User manual](./docs/AKDesk-Fixed-v1.1.0-用户手册.md) · [Test cases](./docs/AKDesk-Fixed-v1.1.0-测试用例清单.md)
- [Release and acceptance](./docs/AKDesk-Fixed-v1.1.0-发布与验收记录.md) · [Changelog](./CHANGELOG.md) · [Roadmap](./ROADMAP.md)
- [Report a bug/data issue](https://github.com/raistlinsha-plus/akdesk-fixed/issues/new/choose) · [Describe your workflow](https://github.com/raistlinsha-plus/akdesk-fixed/discussions/16)

Include the task, steps, expected/actual behavior, version and mode. Do not upload API keys, local databases or confidential research.

## Development and reproduction

Backend:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock -r backend/requirements-dev.txt
PYTHONPATH=backend:. .venv/bin/python -m pytest backend/tests
```

Frontend and static demo:

```bash
cd frontend
npm ci
npm run check
npm run build:demo
npm run preview:demo
```

Standard-library example: `python3 examples/fixed_income_brief.py --output brief-example.md`. Optional live mode is explained in [examples/README.md](./examples/README.md). The stack is React/TypeScript/Vite, FastAPI/Python and SQLite.

## License and contributions

Original code is [MIT licensed](./LICENSE). Third-party dependencies and data retain their own terms and attribution requirements; **MIT grants no redistribution rights for third-party data or content**. See [third-party notices](./THIRD_PARTY_NOTICES.md).

Reproducible bugs, documentation fixes, adapter tests and research cases are welcome. Read [CONTRIBUTING](./CONTRIBUTING.md), the [Code of Conduct](./CODE_OF_CONDUCT.md) and the [Security Policy](./SECURITY.md).
