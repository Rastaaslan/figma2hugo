# Real Pages Semantic9 Raw Pack

Offline raw Figma snapshots for the strict pipeline release gate.

Source run:

```powershell
python scripts\release_gate.py .figma2hugo-scratch\release-gate-all-pages-20260510-responsive-contract-semantic9 --page-file .figma2hugo-scratch\real-figma\pages.txt --cache-dir .figma2hugo-scratch\raw-cache --smoke-out .figma2hugo-scratch\release-gate-all-pages-20260510-responsive-contract-semantic9-smoke --widths 1920,1440,1280,1024,834,402 --screenshot-widths 1920,1440,1280,1024,834,402 --baseline-dir baselines\visual\pipeline\real-pages-semantic5-20260510 --diff-review-threshold 0.002 --diff-fail-threshold 0.01 --review-baseline baselines\review\pipeline\real-pages-semantic9-contract-actionables.json --responsive-contract baselines\review\pipeline\real-pages-responsive-contract.json
```

Release gate command:

```powershell
python scripts\release_gate.py .figma2hugo-scratch\release-offline-semantic10-zero-actionables --raw-dir baselines\raw\pipeline\real-pages-semantic9-20260510 --smoke-out .figma2hugo-scratch\release-offline-semantic10-zero-actionables-smoke --widths 1920,1440,1280,1024,834,402 --screenshot-widths 1920,1440,1280,1024,834,402 --baseline-dir baselines\visual\pipeline\real-pages-semantic5-20260510 --diff-review-threshold 0.002 --diff-fail-threshold 0.01 --review-baseline baselines\review\pipeline\real-pages-semantic10-zero-actionables.json --responsive-contract baselines\review\pipeline\real-pages-responsive-contract.json
```

Refresh this pack only when the source Figma pages intentionally change, then
refresh the visual baseline, responsive contract and review baseline in the same
promotion pass.
