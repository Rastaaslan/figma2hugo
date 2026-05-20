# Project Quality Grid

This grid is the contract used to score `figma2hugo`.

The score can honestly be `100%` only for the supported scope documented in
`README.md`, `SPEC.md` and `docs/figma-authoring-contract.md`. Universal
design-to-code conversion for every possible absolute Figma file is explicitly
outside that contract and is therefore not part of this score.

## Scoring Rule

`100%` means:

- the supported behavior is implemented
- the behavior is covered by automated tests, validation, or an explicit
  documented contract
- the repository quality gate is green
- the limitation, when one exists, is documented as out of scope instead of
  being hidden

Anything outside the support matrix is not downgraded inside this grid; it must
be tracked as future product scope.

## Current Supported-Scope Scores

| Axis | Score | Evidence |
| --- | ---: | --- |
| Figma extraction and render plan | 100% | Raw snapshots, URL parsing, REST fetcher, semantic wrappers, diagnostics for unsupported visible leaves |
| Hugo generation | 100% | The pipeline writes Hugo content, data, layouts, assets and static files directly in the generated site |
| Standalone HTML/CSS generation | Out of scope | Removed with the historical generators; Hugo is the official output |
| Responsive supported scope | 100% | Multi-variant merge, board split, supported flow components, six viewport probes, strict matching mode |
| Supported components | 100% | Accordions, link grids, link cards, component lists, carousels, forms, section blocks |
| Validation and reporting | 100% | Hugo build, asset/text checks, responsive probes, interaction probes, structured JSON and Markdown reporting |
| Automated tests | 100% | Full pytest suite, lint, format and mypy |
| Packaging | 100% | Runtime Python package builds as a wheel; generated Hugo templates are emitted by pipeline |
| Security and secrets hygiene | 100% | Local token config ignored, example config only, no hardcoded project tokens in source |
| Documentation | 100% | README, SPEC, user/technical notice, Figma authoring contract, naming conventions, architecture reference, debug map, quality grid |
| CI and release readiness | 100% | GitHub Actions quality gate covers install, lint, format, typecheck, tests, release gate, perf smoke and wheel build |
| Performance guardrails | 100% | Official pipeline focused imports, asset reuse, cached raw fetches, browser smoke scoped to supported probes |
| CLI and desktop UI | 100% | Main commands, `build-site` and `build` routed to pipeline, report, batch launcher, token-aware Tk UI |
| Project hygiene | 100% | Scratch outputs ignored, generated site ignored, mojibake and hardcoded-project checks covered |

## Out Of Contract

These items are future scope, not failures of the current score:

- automatic conversion of every arbitrary absolute Figma page into a fully
  fluid semantic layout
- pixel-perfect responsive synthesis when no breakpoint variant or supported
  component structure exists
- full prototype-flow conversion into application state machines
- proprietary design-system mapping without an explicit component contract
- CI deployment to a hosting platform

## Required Green Gate

The supported-scope grid stays at `100%` only when all of these pass:

```bash
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src/figma2hugo
python -m pytest -p no:cacheprovider
python scripts/perf_smoke.py --skip-hugo --budget cli_help=3
python -m pip wheel . --no-deps -w .figma2hugo-scratch/ci-wheel
```

For a promoted pipeline generated local site, add:

```bash
PYTHONPATH=src python -m figma2hugo.cli build-site site --page-file .figma2hugo-scratch/real-figma/pages.txt
PYTHONPATH=src python -m figma2hugo.cli visual-smoke site --out .figma2hugo-scratch/real-figma/pipeline-smoke
```

The pipeline promotion gate is green only when the generated `report.json` has
`diagnostics.issueCount=0` and `responsive.issueCount=0`, and the smoke report
has `issueCount=0`, `errorCount=0` and `warnCount=0`. Remaining responsive
signals must be explicitly non-blocking review information.

New generation capabilities belong to pipeline. The quality score assumes the public
Hugo generation path, smoke, baselines and review gates are all evaluated
through pipeline.



