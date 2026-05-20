# figma2hugo

`figma2hugo` genere un site Hugo a partir de pages Figma. Le pipeline actuel
est la version officielle.

## Principe

Figma est la source de verite pour la structure, les breakpoints, les tailles,
les couleurs, les polices et les espacements. Le generateur ne corrige le rendu
que pour des besoins web generiques :

- rails et contraintes globales ;
- composants interactifs ;
- compatibilite navigateur ;
- conversion native des formulaires ;
- garde-fous anti-overflow.

## Installation

```bash
python -m pip install -e .[dev]
python -m playwright install chromium
```

Hugo doit etre disponible dans le `PATH`.

## UI

```bash
figma2hugo-ui
```

L'UI utilise le pipeline pour le bouton `Generer Hugo`.

## CLI

Une page :

```bash
figma2hugo build "<figma-url>" ./site
```

Plusieurs pages :

```bash
figma2hugo build-site ./site --page-file ./pages.txt
```

Depuis des snapshots raw Figma deja exportes :

```bash
figma2hugo build-site ./site --raw ./page-accueil.raw.json
```

## Validation

```bash
python -m pytest
hugo --quiet -s site --cleanDestinationDir
figma2hugo visual-smoke site --out .figma2hugo-scratch/final-smoke
```

## Documentation

- `docs/notice-utilisateur-technique.md`
- `docs/figma-authoring-contract.md`
- `docs/figma-page-architecture-reference.md`
- `docs/figma-naming-conventions.md`
- `docs/debug-function-map.md`
- `docs/project-quality-grid.md`
