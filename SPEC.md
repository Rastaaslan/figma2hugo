# `figma2hugo`

## 1. Objet

Construire un outil en ligne de commande capable de prendre en entrée une URL Figma pointant vers une page complète et de générer :

- soit un projet `Hugo` buildable ;
- soit un export statique `HTML + CSS + assets` ;
- avec extraction des textes, assets, styles, sections, et structure sémantique.

L'objectif est de produire une intégration exploitable et maintenable, pas uniquement une reproduction visuelle ponctuelle.

## 2. Objectifs

- Extraire une page Figma complète de manière fiable.
- Décomposer la page en sections logiques exploitables.
- Générer une sortie propre pour `Hugo` ou en `HTML/CSS` statique.
- Produire un CSS lisible, segmenté et maintenable.
- Télécharger et référencer correctement les assets.
- Conserver l'accessibilité de base du HTML généré.
- Fournir un cadre strict pour une implémentation assistée par IA.

## 3. Périmètre

### Inclus

- Landing page desktop one-page.
- Lecture de frames/pages Figma via MCP.
- Extraction des textes visibles, styles, tokens et assets.
- Détection des sections principales.
- Génération `Hugo`.
- Génération `static HTML/CSS`.
- Validation build et validation visuelle simple.
- Rapport JSON de génération.

### Exclus du MVP

- Responsive pixel-perfect multi-breakpoints.
- Interactions JS avancées issues de prototypes Figma.
- Mapping complet à un design system propriétaire.
- Publication CI/CD.
- Génération d'un back-office ou d'un CMS.

## 4. Technologies nécessaires

### Runtime et outils système

- `Python 3.11+`
- `Hugo CLI 0.156+`
- accès au **Figma MCP Remote Server** ou à une couche compatible exposant les outils requis ;
- accès réseau pour télécharger les assets ;
- environnement `Windows`, `macOS` ou `Linux`.

### Bibliothèques Python obligatoires

- `typer`
- `pydantic`
- `httpx`
- `lxml`
- `jinja2`
- `pillow`
- `playwright`

### Bibliothèques et outils optionnels

- `pytest`
- `ruff`
- `mypy`
- `deepdiff`
- `svgo` ou équivalent pour l'optimisation SVG
- `uv` ou `poetry` pour la gestion d'environnement

### Outils de validation

- `Playwright` avec au minimum `Chromium` installé
- `Hugo` disponible dans le `PATH`

## 5. Dépendances externes structurantes

### Figma MCP

L'outil doit s'appuyer en priorité sur les capacités du **Figma MCP Server**, notamment :

- `get_metadata`
- `get_design_context`
- `get_variable_defs`
- `get_screenshot`

Le Remote MCP server est la source recommandée pour les lectures complètes de fichiers Figma.

### Hugo

La génération `Hugo` doit s'appuyer sur les conventions natives :

- templates dans `layouts/`
- partials dans `layouts/partials/`
- données dans `data/`
- assets statiques dans `static/`

L'accès aux données doit être compatible avec `hugo.Data`.

## 6. Entrées

- `figma_url`
- `output_mode`: `hugo | static`
- `fidelity_mode`: `exact | balanced | semantic`
- `asset_mode`: `svg-first | raster-first | mixed`
- `content_mode`: `inline | data-file`
- `target_dir`

## 7. Sorties

### Mode `hugo`

- `layouts/index.html`
- `layouts/partials/...`
- `assets/css/main.css`
- `data/page.json`
- `static/images/...`
- `report.json`

### Mode `static`

- `index.html`
- `styles.css`
- `images/...`
- `page.json`
- `report.json`

## 8. Exigences fonctionnelles

L'outil doit :

1. parser une URL Figma et extraire `fileKey` et `nodeId` ;
2. lire la structure globale via `get_metadata` ;
3. découper la page en sections candidates ;
4. lire le détail de chaque section via `get_design_context` ;
5. extraire les variables et tokens via `get_variable_defs` quand disponible ;
6. télécharger les assets référencés ;
7. extraire tous les textes visibles avec respect des retours à la ligne ;
8. identifier les composants répétés et les groupes décoratifs ;
9. générer un DOM sémantique : `header`, `section`, `article`, `nav`, `form`, `footer` ;
10. générer un CSS lisible, structuré par section ;
11. gérer les cas complexes : masks, overlays, foregrounds, SVG, z-index, object-fit ;
12. produire un rapport listant ce qui est exact, approximé, ambigu ou manquant.

## 9. Exigences non fonctionnelles

- Fidélité desktop élevée.
- Sortie relisible humainement.
- Build Hugo sans erreur.
- Idempotence raisonnable d'un run à l'autre.
- Logs détaillés.
- Tolérance aux maquettes Figma imparfaites.
- Pas de dépendances front non justifiées.

## 10. Architecture attendue

```text
src/
  cli.py
  config.py
  figma_reader/
  asset_downloader/
  layout_analyzer/
  content_extractor/
  model/
  generators/
    hugo/
    static/
    css/
  validator/
  reporting/
tests/
templates/
  hugo/
  static/
```

## 11. Modèle intermédiaire obligatoire

L'outil doit construire un modèle intermédiaire JSON stable avant toute génération.

Exemple minimal :

```json
{
  "page": {
    "id": "3:964",
    "name": "Page",
    "width": 1920,
    "height": 7422
  },
  "sections": [],
  "texts": {},
  "assets": [],
  "tokens": {
    "colors": {},
    "spacing": {},
    "typography": {}
  },
  "warnings": []
}
```

## 12. Schéma logique du modèle intermédiaire

### `page`

- identifiant Figma
- nom du frame ou de la page
- largeur / hauteur
- méta d'origine

### `sections`

Chaque section doit contenir au minimum :

- `id`
- `name`
- `role`
- `bounds`
- `children`
- `texts`
- `assets`
- `decorative_assets`

### `texts`

Chaque texte doit pouvoir conserver :

- sa valeur brute
- ses retours à la ligne
- éventuellement ses `styleRuns`
- sa section parente

### `assets`

Chaque asset doit pouvoir conserver :

- son `nodeId`
- son URL source
- son format
- son chemin local
- sa fonction estimée : `content | decorative | mask | background | icon`

### `tokens`

Le modèle doit agréger :

- couleurs
- espacements
- typographies
- ombres
- rayons

## 13. Pipeline

1. Parser l'URL Figma.
2. Récupérer metadata et screenshot global.
3. Identifier les sections candidates.
4. Extraire le contexte détaillé par section.
5. Télécharger les assets.
6. Construire le modèle intermédiaire.
7. Générer la sortie `hugo` ou `static`.
8. Générer le CSS.
9. Lancer la validation build + screenshot.
10. Produire `report.json`.

## 14. Règles de génération

- Un frame principal devient une `section`.
- Un groupe purement décoratif devient un asset `aria-hidden`.
- Un texte multi-style devient des `span` ou un partial dédié.
- Un composant répété devient un partial, une macro ou un bloc réutilisable.
- Les formulaires doivent garder de vrais `label`.
- Les SVG Figma complexes doivent être réutilisés comme assets plutôt que reconstruits approximativement.
- Les contenus éditoriaux doivent pouvoir être externalisés dans `data/page.json`.
- Les éléments non sémantiques issus de Figma ne doivent pas être recopiés à l'identique si une structure HTML plus correcte existe.

## 15. Règles spécifiques de sortie Hugo

- Les templates HTML doivent vivre dans `layouts/`.
- Les partials doivent être créés si plusieurs sections ou motifs sont réutilisables.
- Les données doivent être accessibles via `hugo.Data`.
- Les assets doivent être placés dans `static/images/`.
- Le CSS principal doit être centralisé dans `assets/css/main.css`, sauf besoin fort de découpage.

## 16. Règles spécifiques de sortie statique

- Générer un `index.html` unique pour le MVP.
- Générer un `styles.css` unique pour le MVP.
- Les assets doivent être placés dans `images/`.
- Aucun framework JS ou CSS ne doit être ajouté par défaut.

## 17. Validation

L'outil doit exécuter les contrôles suivants :

- build `hugo` si le mode est `hugo` ;
- vérification de présence des assets ;
- vérification de présence des textes visibles ;
- validation du modèle intermédiaire via `Pydantic` ;
- comparaison visuelle via screenshot `Playwright` contre une référence locale ;
- génération d'un rapport final.

Exemple de `report.json` :

```json
{
  "buildOk": true,
  "visualScore": 0.91,
  "missingAssets": [],
  "missingTexts": [],
  "warnings": []
}
```

## 18. CLI attendue

```bash
figma2hugo inspect <figma-url>
figma2hugo extract <figma-url> --out .cache/run
figma2hugo generate <figma-url> --mode hugo --out ./site
figma2hugo generate <figma-url> --mode static --out ./dist
figma2hugo validate ./site --against <figma-url>
figma2hugo report ./site
```

## 19. Critères d'acceptation

- Une URL Figma valide produit une sortie buildable.
- Tous les textes visibles sont extraits.
- Tous les assets visibles sont présents.
- Les sections principales sont correctement identifiées.
- Le DOM final est sémantique.
- Le CSS final reste maintenable.
- Le rapport liste clairement les ambiguïtés.

## 20. Utilisation avec une IA

Ce document est conçu pour être donné à une IA comme **spécification stricte**, pas comme brief vague.

### Règles à imposer à l'IA

- Travailler par étapes.
- Ne jamais sauter le modèle intermédiaire.
- Ne jamais inventer de modules hors spec.
- Générer du code seulement après avoir proposé l'arborescence et les schémas.
- Vérifier chaque étape contre les critères d'acceptation.
- Produire du JSON valide pour les structures intermédiaires.
- Ne pas introduire de logique d'agent autonome.

### Ordre de travail recommandé pour l'IA

1. proposer l'arborescence projet ;
2. écrire les modèles `Pydantic` ;
3. implémenter le parsing URL Figma ;
4. implémenter le lecteur Figma ;
5. implémenter le modèle intermédiaire ;
6. implémenter le générateur `static` ;
7. implémenter le générateur `Hugo` ;
8. implémenter la validation et le rapport.

### Prompt maître recommandé

```text
Tu dois implémenter un outil Python nommé figma2hugo selon le SPEC fourni.
Respecte strictement le périmètre.
Travaille par étapes.

Commence par :
1. proposer l’arborescence du projet ;
2. définir les modèles Pydantic ;
3. définir les commandes Typer.

Ne génère pas encore le reste du code.
Attends validation logique après chaque étape.
```

## 21. Livrable MVP

- support d'une landing page desktop one-page ;
- mode `hugo` ;
- mode `static` ;
- extraction textes / assets / sections ;
- génération CSS maintenable ;
- `report.json` ;
- validation visuelle simple.

## 22. Références techniques

- Figma MCP introduction : https://developers.figma.com/docs/figma-mcp-server/
- Figma MCP tools : https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/
- Hugo templating : https://gohugo.io/templates/introduction/
- Hugo data access : https://gohugo.io/functions/hugo/data/
- Typer : https://typer.tiangolo.com/
- Pydantic : https://pydantic.dev/docs/validation/latest/concepts/models/
- HTTPX : https://www.python-httpx.org/
- lxml : https://lxml.de/
- lxml parsing : https://lxml.de/parsing.html
- Jinja : https://jinja.palletsprojects.com/en/stable/
- Pillow : https://pillow.readthedocs.io/en/stable/
- Playwright visual comparisons : https://playwright.dev/docs/test-snapshots
