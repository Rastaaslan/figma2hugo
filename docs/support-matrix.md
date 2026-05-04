# Support Matrix

Ce document fige le perimetre actuellement supporte par `figma2hugo`.

## Strategie generale

- Rendu **desktop-first** fidele a Figma par defaut
- Blocs **responsive-friendly** actives de maniere ciblee via le layout et les conventions de nommage
- Validation automatique du build, des assets, des textes, du responsive multi-viewports et des interactions cles

## Stable aujourd'hui

- Generation statique
- Generation Hugo mono-page et multi-pages
- Extraction des textes, assets et wrappers semantiques
- FAQ / accordions
- Matrices de `href-card` / `link-grid`
- Carrousels
- Formulaires HTML basiques enrichis
- Sous-sections `section-block` en flux opt-in
- Fusion responsive multi-variantes basee sur les noms de pages `page-<slug>-<width>`

## Responsive-friendly garanti

- Shell desktop fixe conserve tant qu'aucun mode flow n'est explicitement demande
- Validation multi-breakpoints sur :
  - `1440`
  - `1280`
  - `1024`
  - `768`
  - `390`
- Sondes d'interaction sur :
  - accordions
  - link cards
  - carrousels
  - formulaires

## Non garanti pour l'instant

- Conversion automatique de n'importe quelle page absolue Figma en layout web fluide
- Resize ou adaptation automatique des maquettes entre largeurs
- Responsive global complet sans conventions de structure explicites
