# figma2hugo

## Objet

`figma2hugo` transforme des pages Figma en site Hugo via le pipeline.

Figma est la source de verite pour le contenu, les breakpoints, les dimensions,
les couleurs, la typographie et l'intention visuelle. Le code n'applique des
ajustements que pour les besoins web generiques :

- rails et contraintes globales ;
- composants interactifs ;
- compatibilite navigateur ;
- conversion native des formulaires ;
- garde-fous anti-overflow generiques.

## Perimetre Officiel

Inclus :

- generation Hugo mono-page et multi-pages ;
- lecture de pages Figma par URL ou par snapshots raw ;
- fusion responsive des frames `page-<slug>-<width>` ;
- composants interactifs supportes : formulaires, accordions, carrousels,
  link cards ;
- rapports JSON pipeline ;
- smoke navigateur Playwright/static fallback ;
- baselines visuelles et baselines de revue.

Exclus :

- generation HTML autonome hors Hugo ;
- anciens workflows historiques ;
- anciens generateurs historiques ;
- conversion universelle de toute maquette Figma sans contrat de structure ;
- publication CI/CD.

## Entrees

- une ou plusieurs URLs Figma avec `node-id` ;
- ou un ou plusieurs fichiers `*.raw.json` ;
- un dossier de destination Hugo ;
- optionnellement un token Figma, un cache raw et des contrats responsive.

## Sortie Hugo

Le site genere suit l'idiome Hugo :

```text
site/
  hugo.toml
  content/
  data/pipeline/
  layouts/
  assets/
  static/pipeline-assets/
  report.json
```

## Commandes Officielles

```bash
figma2hugo build "<figma-url>" ./site
figma2hugo build-site ./site --page-file ./pages.txt
figma2hugo build-site ./site --raw ./page.raw.json
figma2hugo visual-smoke ./site --out .figma2hugo-scratch/smoke
figma2hugo report ./site
figma2hugo-ui
```

## Architecture Runtime

```text
src/figma2hugo/
  cli.py
  config.py
  gui.py
  gui_presenter.py
  local_config.py
  progress.py
  pipeline/
```

Les modules hors `pipeline` servent uniquement aux entrypoints, a l'UI, a la
configuration locale et a l'affichage de progression.

## Gate Qualite

Le projet est valide quand les controles suivants passent :

```bash
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src/figma2hugo
python -m pytest -p no:cacheprovider
python scripts/perf_smoke.py --skip-hugo --budget cli_help=3
python -m pip wheel . --no-deps -w .figma2hugo-scratch/ci-wheel
```

Pour un site genere :

```bash
hugo --quiet -s site --cleanDestinationDir
figma2hugo visual-smoke site --out .figma2hugo-scratch/final-smoke
```
