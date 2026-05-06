# Support Matrix

Ce document fige le perimetre actuellement supporte par `figma2hugo`.

## Strategie generale

- Rendu **desktop-first** fidele a Figma par defaut
- Blocs **responsive-friendly** actives de maniere ciblee via le layout et les conventions de nommage
- Validation automatique du build, des assets, des textes, du responsive multi-viewports et des interactions cles
- Le responsive multi-variantes reste dans l'idiome Hugo :
  - une page finale = une route Hugo normale
  - les donnees fusionnees restent dans `data/`
  - le rendu reste dans `layouts/` et `partials/`
  - le CSS reste dans `assets/css/`
  - aucun merge layout n'est delegue au navigateur

## Stable aujourd'hui

- Generation statique
- Generation Hugo mono-page et multi-pages
- Extraction des textes, assets et wrappers semantiques
- FAQ / accordions
- Matrices de `href-card` / `link-grid`
- Collections de composants repetitifs detectees (`component-list`)
- Carrousels
- Formulaires HTML basiques enrichis
- Sous-sections `section-block` en flux opt-in
- Fusion responsive multi-variantes basee sur les noms de pages `page-<slug>-<width>`
- Une famille responsive fusionnee produit une seule page Hugo finale, une seule feuille CSS finale et un seul JSON final
- Un board Figma unique peut contenir plusieurs frames top-level `page-<slug>-<width>` et sera splitte automatiquement avant fusion

## Responsive-friendly garanti

- Shell desktop fixe conserve tant qu'aucun mode flow n'est explicitement demande
- Validation multi-breakpoints sur :
  - `1920`
  - `1440`
  - `1280`
  - `1024`
  - `834`
  - `402`
- Sondes d'interaction sur :
  - accordions
  - link cards
  - carrousels
  - formulaires

## Non garanti pour l'instant

- Conversion automatique de n'importe quelle page absolue Figma en layout web fluide
- Resize ou adaptation automatique des maquettes entre largeurs
- Responsive global complet sans conventions de structure explicites
- Merge fiable si les noms de pages ou la structure partagee divergent entre variantes
