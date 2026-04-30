# Support Matrix

Ce document fige le périmètre actuellement supporté par `figma2hugo`.

## Stratégie générale

- Rendu **desktop-first** fidèle à Figma par défaut
- Blocs **responsive-friendly** activés de manière ciblée via le layout et les conventions de nommage
- Validation automatique du build, des assets, des textes, du responsive multi-viewports et des interactions clés

## Stable aujourd'hui

- Génération statique
- Génération Hugo mono-page et multi-pages
- Extraction des textes, assets et wrappers sémantiques
- FAQ / accordéons
- Matrices de `href-card` / `link-grid`
- Carrousels
- Formulaires HTML basiques enrichis
- Sous-sections `section-block` en flux opt-in

## Responsive-friendly garanti

- Shell desktop fixe conservé tant qu'aucun mode flow n'est explicitement demandé
- Validation multi-breakpoints sur :
  - `1440`
  - `1280`
  - `1024`
  - `768`
  - `390`
- Sondes d'interaction sur :
  - accordéons
  - link cards
  - carrousels
  - formulaires

## Non garanti pour l'instant

- Conversion automatique de n'importe quelle page absolue Figma en layout web fluide
- Fusion automatique de plusieurs variantes Figma d'une même page pour produire les breakpoints
- Responsive global complet sans conventions de structure explicites
