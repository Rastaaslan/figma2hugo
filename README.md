# figma2hugo

`figma2hugo` is a Python CLI that reads a Figma landing page, builds a stable intermediate JSON model, and generates either:

- a Hugo project
- or a static `HTML + CSS + assets` export

## What Works

- `inspect`, `extract`, `generate`, `validate`, `report`
- stable intermediate model in `page.json`
- section, text, asset, and token extraction heuristics
- Hugo and static generators driven by Jinja/Hugo templates
- asset download and copy into generated outputs
- Hugo build validation
- optional screenshot comparison when a Figma reference image is available

## Requirements

- Python `3.11+`
- Hugo CLI in `PATH`
- `FIGMA_ACCESS_TOKEN` for structured REST extraction
- optional: `mcp` extra plus `FIGMA_MCP_*` environment variables for an MCP-compatible bridge

## Install

```bash
python -m pip install -e .[dev]
```

Optional MCP support:

```bash
python -m pip install -e .[mcp]
```

Optional Playwright browser install:

```bash
python -m playwright install chromium
```

## Usage

```bash
lancer-figma2hugo.bat
figma2hugo-ui
figma2hugo build "https://www.figma.com/design/FILEKEY/Page?node-id=3-964" ./site
figma2hugo generate "https://www.figma.com/design/FILEKEY/Page?node-id=3-964" ./site
figma2hugo generate "https://www.figma.com/design/FILEKEY/Page?node-id=3-964" ./dist --mode static
figma2hugo inspect "https://www.figma.com/design/FILEKEY/Page?node-id=3-964"
figma2hugo extract "https://www.figma.com/design/FILEKEY/Page?node-id=3-964" --out ./figma-extract
figma2hugo validate ./site --against "https://www.figma.com/design/FILEKEY/Page?node-id=3-964"
figma2hugo report ./site
```

## Main Workflow

For the normal use case, you only need:

```bash
lancer-figma2hugo.bat
```

ou:

```bash
figma2hugo-ui
```

Or, if you prefer the terminal:

```bash
figma2hugo build "<figma-url>" "<destination-folder>"
```

This does all of the following:

1. reads the Figma page from the URL
2. extracts sections, texts, assets, and tokens into an intermediate model
3. generates a Hugo site in the destination folder by default
4. validates the generated output
5. writes a `report.json`

If you want the static export instead of Hugo:

```bash
figma2hugo generate "<figma-url>" "<destination-folder>" --mode static
```

## User Interface

The desktop UI is built with `tkinter` and focuses on the two inputs you asked for:

- the Figma URL
- the destination folder

From there, you can:

- generate a Hugo project
- export a static site
- open the generated folder
- read the result summary and the generation report directly in the app

Important:

- the UI still needs Figma access to read the design
- the simplest option is to paste a Figma personal access token into the `Token Figma` field
- you can also place it in `figma2hugo.local.json` at the root of the project
- alternatively, you can define `FIGMA_ACCESS_TOKEN` in your environment or configure a compatible MCP bridge

Example local config file:

```json
{
  "figma_access_token": "ton_token_ici"
}
```

An example file is available at `figma2hugo.local.example.json`.

## Notes

- The REST path is the most reliable structured source today.
- The MCP client is implemented as a best-effort adapter for a compatible bridge, because auth and transport can vary by setup.
- Section detection and semantic mapping are heuristic in the MVP and can be refined section by section over time.

## Figma Coverage

These coverage notes apply to both export modes because extraction, normalization, asset handling, and CSS generation are shared between static and Hugo. Differences that remain output-specific mostly live in the final HTML template layer.

What the exporter handles best today:

- classic landing pages and marketing pages built from `FRAME`, `GROUP`, `SECTION`, `RECTANGLE`, `VECTOR`, and `TEXT`
- image fills, local asset rendering, and mixed `SVG` / `PNG` exports
- masked groups rendered as composite raster assets when the node structure is compatible
- decorative overlays and foreground layers when their structure or stacking order makes that intent detectable
- absolute-position visual exports for static HTML and Hugo
- generated HTML references assets as external files instead of inlining raw Figma SVG fragments into the page markup

What remains heuristic or partial:

- section detection still depends on page structure, bounds, and some semantic hints
- auto-layout is flattened into absolute placement, not re-authored as semantic layout code
- component semantics, variants, interactive states, and prototype flows are not exported as rich code abstractions
- complex blend modes, advanced effects, and some imported vector / clip-path constructions can still vary depending on how Figma exposes them through the API
- unsupported visible leaf node types are now reported as warnings instead of failing silently

What the real Hugo build is specifically checked for in tests:

- semantic section and text tags remain valid HTML after Hugo templating instead of being escaped as text
- styled text segments survive Hugo escaping rules
- mask-only assets are omitted from final markup
- external `SVG` and raster assets stay referenced through `<img>` tags rather than being expanded inline into the HTML
