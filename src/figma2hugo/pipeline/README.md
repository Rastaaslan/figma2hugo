# pipeline

This package contains the clean rules and contracts for the official
generation pipeline.

The pipeline path starts from raw Figma-like nodes and owns its own normalized tree,
responsive manifest and render plan. The core pipeline modules must stay autonomous
and must not call historical canonical builders, responsive mergers or
template/runtime repair code.

Production status:

- `build-site` is the recommended multi-page generation path and resolves to pipeline
  by default.
- `build <figma-url> <out>` is the recommended single-page generation path and
  also resolves to pipeline by default.
- Tooling uses the official public names: `build`, `build-site`,
  `build-figma`, `build-raw`, `visual-smoke`,
  `promote-visual-baseline`, and `promote-review-baseline`.
- Builds started from Figma URLs write a `figmaReference` plan into
  `report.json`. `visual-smoke` uses it as the first-run visual reference when
  no approved project baseline exists.
- `build-site` is also the raw-file final-site entrypoint through `--raw`.
- Figma is the source of truth for content, structure, breakpoints and visual
  intent, except for interactive web components that must remain usable,
  accessible and testable in the browser.

Architecture contract:

- `pipeline` must not import historical workflow/generator/extractor/reader
  stacks or historical templates.
- The CLI and UI route Hugo generation to pipeline entrypoints. Historical shims are
  not shared orchestration layers for pipeline.
- pipeline may apply deterministic semantic readability/layout adjustments inside the
  render plan when faithful Figma geometry would produce unusable HTML. Those
  adjustments must be bounded, reported as review diagnostics, and must not use
  runtime repair code from older flows.
- The final pipeline Hugo writer owns only pipeline-managed output zones:
  `data/pipeline`, `assets/css/pipeline`, `static/pipeline-assets`, `layouts/partials/pipeline`, and
  generated content pages marked with `pipelinePageKey` or `pipelineResponsiveKey`.
- User-facing structure and workflow references live in
  `docs/figma-page-architecture-reference.md` and
  `docs/notice-utilisateur-technique.md`.
- Debug function mapping lives in `docs/debug-function-map.md`.

- `geometry.py`: board and section snapping rules.
- `models.py`: raw/normalized/render-plan contracts.
- `normalizer.py`: raw Figma-like tree to explicit page-coordinate tree.
- `diagnostics.py`: structured layout issues such as board overflow, large gaps and clipped content.
- `export.py`: JSON-compatible pipeline manifests for tests and diagnostics.
- `fetcher.py`: standalone Figma REST raw-node fetcher.
- `figma_references.py`: plans and prepares Figma PNG references for
  first-run visual comparison.
- `html_renderer.py`: standalone HTML/CSS render harness for the pipeline render plan.
- `runner.py`: file-based pipeline entrypoint, raw JSON to pipeline artifacts. The final-site path groups responsive variants by page family before rendering.
- `responsive_identity.py`: stable breakpoint render identities.
- `responsive.py`: structured responsive manifest and issue decisions.
- `render_plan.py`: render-facing plan derived from normalized geometry.
- `review_baselines.py`: project-scoped review/responsive contract baseline
  promotion and resolution, keyed by `sourceIdentity.projectId`.
- `semantic_adjustments.py`: deterministic render-plan transforms for bounded semantic fixes, currently tiny mobile form controls, bottom-anchored section content after expansion, closed accordion compaction, text intrinsic-height fallback, legal footer readability and semantic section reflow. Name-based behavior must stop at generic semantic inference: `contact` or `zone-*` alone must not trigger form layout logic.
- `orchestrator.py`: clean entrypoint for the pipeline flow.
- `site_renderer.py`: small standalone static site writer from pipeline render plans.
- `hugo_renderer.py`: Hugo-native pipeline writer using `content/`, `data/`, `layouts/` and `assets/css/`.

CLI entrypoints:

- `build-raw --out <dir> <raw.json>...`: debug harness that writes raw render plans, standalone HTML, static preview and Hugo preview.
- `build-figma --out <dir> <figma-url>...`: same debug harness, starting from Figma REST URLs.
- `build-site <out> --page-file <pages.txt>`: recommended multi-page command routed to the final Hugo pipeline site writer.
- `build <figma-url> <out>`: recommended single-page command routed to the final Hugo pipeline site writer.
- `build-site <out> --page <figma-url>...`: direct final Hugo pipeline writer. It writes the Hugo site directly in `<out>`, keeps raw/plans/diagnostics in `<out>/.figma2hugo-pipeline-debug`, and accepts several responsive page families in one run.
- `build-site <out> --raw <raw.json>...`: same final Hugo pipeline writer from raw JSON files.
- `visual-smoke <pipeline-hugo-site> --out <dir>`: compiles the generated Hugo pipeline site, serves it locally, runs Chromium checks across the responsive widths, and writes `report.json`, `issues.json`, screenshots, `review.html`, `contact-sheet.png` and `visual-baseline-manifest.json`.
- `visual-smoke <pipeline-hugo-site> --out <dir>`: when no project visual baseline is available, it exports planned Figma PNG references and compares Hugo screenshots against those before falling back to capture-only mode.
- `visual-smoke` uses `--browser-engine auto` by default. If Python Playwright cannot start the browser driver, `auto` falls back to static HTML checks and records `browser.engine: static-fallback` in `report.json`; use `--browser-engine playwright` for strict browser-only runs or `--browser-engine static` to bypass Playwright intentionally.
- `visual-smoke` supports portable visual baselines with `--baseline-mode off|capture|compare|auto`, `--baseline-root <dir>` and `--baseline-id <snapshot>`. `auto` compares against the current snapshot for the generated project's `sourceIdentity` when one exists; otherwise it records a bootstrap capture instead of comparing against an unrelated project.
- `promote-visual-baseline <smoke-out> --baseline-root <dir>` promotes a reviewed smoke run into `baseline-root/<project-id>/<snapshot-id>/` and updates that project's `index.json`.
- `promote-review-baseline <site-or-report> --baseline-root <dir>` promotes the current review signals into `baseline-root/<project-id>/<snapshot>.json`. Responsive `actionable-review` items become strict `responsiveContracts`; optional `--approve-actionable-reviews` can also approve remaining non-responsive P2/P3 fingerprints.
- `build-site` can resolve those project contracts with `--responsive-contract-root <dir>` and optional `--responsive-contract-id <snapshot>`.
- `scripts/release_gate.py <out> --page-file <pages.txt>`: orchestrates the recommended build plus visual smoke and fails if pipeline diagnostics, responsive issues, smoke warnings or smoke errors are non-zero. It also blocks `P0`/`P1` review items, accepts live Figma URLs or offline `--raw`/`--raw-dir` inputs, passes visual baseline options to `visual-smoke`, treats strict compare baseline statuses as blocking, can require known `actionable-review` fingerprints with `--review-baseline` or `--review-baseline-root`, and can require intentional responsive declarations with `--responsive-contract` or `--responsive-contract-root`.

Current real-site validation loop:

```powershell
$env:PYTHONPATH='src'
python -m figma2hugo.cli build-site .figma2hugo-scratch\pipeline-full-site-from-pages-fix3 --page-file .figma2hugo-scratch\real-figma\pages.txt
python -m figma2hugo.cli visual-smoke .figma2hugo-scratch\pipeline-full-site-from-pages-fix3 --out .figma2hugo-scratch\pipeline-full-site-from-pages-fix3-cli-smoke
python scripts\release_gate.py .figma2hugo-scratch\release-pipeline-offline-semantic10-zero-actionables --raw-dir baselines\raw\pipeline\real-pages-semantic9-20260510 --smoke-out .figma2hugo-scratch\release-pipeline-offline-semantic10-zero-actionables-smoke --baseline-dir baselines\visual\pipeline\real-pages-semantic5-20260510 --review-baseline baselines\review\pipeline\real-pages-semantic10-zero-actionables.json --responsive-contract baselines\review\pipeline\real-pages-responsive-contract.json
```

Portable visual baseline workflow for a new project:

```powershell
$env:PYTHONPATH='src'
python -m figma2hugo.cli build-site site --page-file pages.txt --refresh-cache
python -m figma2hugo.cli visual-smoke site --out .figma2hugo-scratch\project-smoke --baseline-mode auto --baseline-root baselines\visual\pipeline\projects
python -m figma2hugo.cli promote-visual-baseline .figma2hugo-scratch\project-smoke --baseline-root baselines\visual\pipeline\projects --label first-approved
python -m figma2hugo.cli visual-smoke site --out .figma2hugo-scratch\project-smoke-compare --baseline-mode compare --baseline-root baselines\visual\pipeline\projects
```

Portable review/responsive contract workflow for a new project:

```powershell
$env:PYTHONPATH='src'
python -m figma2hugo.cli build-site site --page-file pages.txt --refresh-cache
python -m figma2hugo.cli promote-review-baseline site --baseline-root baselines\review\pipeline\projects --label first-approved
python scripts\release_gate.py .figma2hugo-scratch\project-release --page-file pages.txt --baseline-mode compare --baseline-root baselines\visual\pipeline\projects --review-baseline-root baselines\review\pipeline\projects --responsive-contract-root baselines\review\pipeline\projects
```

The build report carries `sourceIdentity.projectId` and `sourceIdentity.sourceHash`.
The project id stays stable for the same Figma file/node set, while the source
hash changes when Figma content changes. This keeps visual baselines and
review/responsive contracts project-scoped instead of tied to the historical
real-pages fixture.

Remaining pipeline rendering rules:

- Semantic rails stabilize recognized sections, backgrounds and components
  without inventing intent that is absent from Figma.
- Accordions, carousels, link cards and forms must remain covered by interaction
  probes.
- Browser compatibility is validated through the browser smoke path when
  available; static fallback is explicitly recorded in reports.
- Native form controls stay native, with bounded readability and placement
  adjustments when Figma dimensions would make them unusable.
- Generic anti-overflow rules contain horizontal spill by semantic role and
  geometry, not by page-specific exceptions.

The smoke report is considered green when `issueCount`, `errorCount` and
`warnCount` are all `0`. Responsive manifest `info` signals stay in the pipeline
build report as design-review signals; they are not treated as rendering
failures. The final build report also includes a `review` summary that classifies
signals as `blocking`, `actionable-review`, `accepted-info` or
`accepted-contract`, and assigns a `P0` to `P3` review priority. Responsive
review items include `differenceKind` when possible, so copy/asset deltas,
missing breakpoint nodes and order-only collection variants can be reviewed
separately. They also carry `contractRule`, `contractAction`, `contractRisk`
and `nodeRole` so Figma authoring fixes can be triaged without adding runtime
Hugo repair logic.

Promotion gate before releasing pipeline as the normal site-generation path:

- Unit, type and lint checks pass.
- Real pages build from the versioned raw pack in
  `baselines/raw/pipeline/real-pages-semantic9-20260510`.
- `visual-smoke` is green on the generated Hugo source.
- In strict compare mode, every captured screenshot must be `pass`; no
  `missing-baseline`, `capture-only`, `height-delta-review`, `review` or `fail`
  status remains.
- In auto mode, a missing project baseline is treated as bootstrap capture and
  must be promoted before strict compare can be used.
- Visual baseline comparison applies a small per-pixel anti-aliasing tolerance
  before the review/fail ratio thresholds, so renderer noise does not mask the
  real gate signal.
- The build report has diagnostic issue count `0` and responsive issue count
  `0`. Review signals may remain only when they are explicitly classified as
  non-blocking, with no `blocking` classification and no unresolved `P0`/`P1`.
- When `--review-baseline` is provided, every current `actionable-review` must
  match an approved fingerprint. Reduced counts are allowed; new or changed
  review signals fail the gate.
- When `--responsive-contract` is provided, every declaration must be valid and
  match a current responsive review signal. Matching signals become
  `accepted-contract`; stale declarations fail the gate.
- The `--review-baseline-root` and `--responsive-contract-root` variants apply
  the same rules after resolving the current project snapshot from
  `sourceIdentity.projectId`.
- Generated assets used by Hugo are stable local URLs under `/pipeline-assets/`
  whenever the source asset can be copied or downloaded.
- The Figma authoring contract in `docs/figma-authoring-contract.md` is
  respected for page widths, stable component identity and semantic layer
  names.



