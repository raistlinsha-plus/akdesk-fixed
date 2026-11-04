# AKDesk v1.1.2: a five-minute reproducible casebook

Historical scope: this casebook was developed locally as v1.1.2 and is included in the v1.2.0 delivery. For current installation and research workflow, see the [v1.2.0 guide](../AKDesk-Fixed-v1.2.0-产品与使用指南.md).

The UI remains primarily Chinese; this English guide covers complete workflows, not a fully translated application. This is a local delivery: check actual Releases/Pages deployment before assuming new public routes are live.

## Start safely

Select **场景案例** (Casebook). Routes: `#/scenarios?q=daily`, `#/scenarios?q=rates`, `#/scenarios?q=credit`. Unknown IDs fall back to the gallery.

All cases use hand-authored synthetic fixtures dated **2026-08-03**. Securities, issuers, ratings and observations are fictional. The case components do not fetch market data, call AI or read/write a research database. The static demo needs no backend, login or key. Local app background services remain separate.

## 1. Daily fixed-income observation

**Question:** Which changes need verification before writing a market note?

1. **观察变化 / Observe:** Read divergent funding tenors, a lower 10Y yield and differing futures directions; expand the supporting arithmetic.
2. **核验数值 / Verify:** Select 1Y, 5Y, 10Y or 30Y. The sample 10Y moves from 1.82% to 1.80%, or **-2 BP**, while 30Y moves **+1 BP**. One BP is 0.01 percentage points.
3. **带走简报 / Take away:** Add a temporary note; copy/download Markdown or print/PDF. Synthetic provenance, observation date and usage notices remain in the output.

**Expected output:** [synthetic brief](../media/v1.1.0/示例-固收简报.md), not a real report for that day. Notes are not saved research entries. Explicitly open local modules to verify authorized real sources and timestamps.

## 2. Follow an interest-rate hypothesis

**Question:** Does the lower long end have consistent support from funding and other maturities?

1. **提出问题 / Frame:** Edit a testable question; a single-day change is not a proven trend.
2. **区分证据 / Classify:** Assign synthetic signals to **支持线索** (support), **反证 / 分歧** (counter-evidence/divergence) or **待核验** (pending). Defaults are teaching examples, not AI conclusions.
3. **安排验证 / Review:** Enter a valid review date after the fixture day and a concrete verification task. Preview/download the draft. The date creates no real reminder.

**Expected output:** [research draft](./AKDesk-v1.1.2-利率研究样例.md) with question, evidence roles, counter-evidence and next verification. No project, evidence or task is automatically inserted. No FRED responses are used.

## 3. Credit coverage and manual review

**Question:** Which of three bond records cannot support a mechanical spread calculation?

1. **预览合成资料 / Preview:** Load the fixed records; optionally download the [synthetic CSV](../../examples/scenarios/credit-review-synthetic.csv). This is a fixed preview, not an arbitrary file validator.
2. **检查覆盖门禁 / Check:** A has aligned dates/tenor: `(2.60 - 1.60) × 100 = 100 BP`. B has no rating; C has a benchmark from a different day. Both remain missing (`—`), never zero or an invented spread.
3. **选择复核任务 / Select:** Select records for human verification, then preview/download a checklist. No selection does not mean no review is necessary.

**Expected output:** [credit checklist](./AKDesk-v1.1.2-信用复核样例.md). Fixed results are contract-tested against actual backend import and coverage rules. They are not ratings, default probabilities or trading recommendations. To try the existing local importer, use an isolated demo data directory and preview only; do not commit synthetic bonds to your real library.

## Feedback and limitations

At the last step, select what actually happened (completed sample, blocker, browsed) and willingness to try again, then preview metadata. Only version, fixed case, synthetic mode, entry surface, outcome and intent enter the GitHub issue URL. Drafts, notes, selections, paths, diagnostics and research content do not.

Opening GitHub is not submission: log in, check and submit yourself. Intent is not retention; synthetic completion is not verified business usage. No default telemetry or automatic model call. Share links include only a canonical case ID.

Drafts survive step changes but clear when leaving, switching cases, resetting or refreshing. Export first if needed. Never paste keys, private material or restricted API content. Local-first/MIT does not grant third-party data rights. See [data rules](../../DATA_USAGE.md) and [Chinese guide](../AKDesk-Fixed-v1.1.2-场景案例与使用指南.md).
