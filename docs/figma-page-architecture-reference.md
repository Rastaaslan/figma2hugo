# Architecture Figma Generique pipeline

Ce document donne une structure de reference pour organiser une maquette Figma
destinee au pipeline. Elle n'est pas limitee aux sites vitrines : elle doit
rester valable pour une page marketing, une app, un dashboard, une fiche
produit, un tunnel d'achat, une documentation ou un back-office.

## Principe

Le nom d'un calque doit dire son intention, pas seulement sa position visuelle.

- `page-*` decrit l'ecran ou la page source.
- `region-*` decrit une zone fonctionnelle d'interface.
- `section-*` decrit un bloc de contenu ou un bloc metier.
- Les enfants decrivent le type de composant : `form-*`, `table-*`,
  `toolbar-*`, `panel-*`, `card-*`, `accordion-*`, `modal-*`, etc.
- Les noms restent stables entre breakpoints quand l'element represente la meme
  intention.

## Structure Complete Exemple

```text
page-<projet-ou-ecran>-1920
  region-app-shell
    bg-app

    nav-primary
      nav-logo
      nav-item-01
      nav-item-02
      nav-user-menu

    header-page
      breadcrumb-page
      titre-h1-page
      texte-intro-page
      toolbar-page-actions
        button-primary-action
        button-secondary-action

    region-main
      section-overview
        titre-h2-overview
        texte-overview
        card-kpi-01
          icon-kpi-01
          titre-h3-kpi-01
          texte-kpi-01
        card-kpi-02
          icon-kpi-02
          titre-h3-kpi-02
          texte-kpi-02

      region-content-list
        toolbar-filtres
          field-search
          select-status
          button-filter-reset
        table-items
          table-header
          table-row-01
            cell-title
            cell-status
            cell-actions
          table-row-02
            cell-title
            cell-status
            cell-actions
        pagination-items

      section-detail
        panel-detail-main
          titre-h2-detail
          texte-detail
          image-detail-main
          gallery-detail
            image-gallery-01
            image-gallery-02
        panel-detail-side
          card-summary
          cta-primary-detail

      section-context-action
        form-context
          label-name
          field-name
          label-email
          field-email
          label-message
          textarea-message
          select-category
          checkbox-consent
          submit-context

      section-help
        accordion-help-01
          accordion-trigger-help-01
          accordion-panel-help-01
        accordion-help-02
          accordion-trigger-help-02
          accordion-panel-help-02

    footer-app
      texte-footer-legal
      link-label-privacy
      link-label-terms

  modal-confirm-action
    titre-h2-modal-confirm
    texte-modal-confirm
    button-cancel
    button-confirm

  drawer-filters
    titre-h2-drawer-filters
    checkbox-filter-01
    checkbox-filter-02
    button-apply-filters

  toast-success
    texte-toast-success

  decor-page-01
  decor-page-02
```

Cette arborescence est volontairement large. Une page reelle n'a pas besoin de
tout contenir. Elle sert de reference pour nommer correctement les elements
quand ils existent.

## Variantes Responsive

Une meme page responsive utilise des frames page separees :

```text
page-dashboard-1920
page-dashboard-834
page-dashboard-402
```

Les enfants gardent le meme nom si leur intention est la meme :

```text
region-main
toolbar-filtres
table-items
form-context
accordion-help-01
```

Seul le frame page porte la largeur. Eviter :

```text
region-main-402
table-items-mobile
card-kpi-01-w834
```

Utiliser un nom specifique seulement quand l'element est vraiment propre a un
breakpoint :

```text
cta-mobile-only
decor-hero-tablette-01
summary-compact-mobile
```

## Prefixes Recommandes

```text
page-*        ecran/page source responsive
region-*      zone fonctionnelle d'interface
section-*     bloc de contenu ou bloc metier
header-*      entete d'ecran ou de zone
footer-*      pied d'ecran ou de zone
nav-*         navigation
toolbar-*     actions ou filtres
panel-*       panneau d'information ou d'action
card-*        item, resume ou bloc repete
table-*       donnees tabulaires
cell-*        cellule de table
pagination-*  pagination
form-*        formulaire
formulaire-*  formulaire, alias francais accepte
field-*       champ texte
select-*      liste/selecteur
textarea-*    zone de texte longue
checkbox-*    case a cocher
submit-*      action de soumission
button-*      bouton generique
accordion-*   groupe accordeon
modal-*       fenetre modale
drawer-*      panneau lateral
toast-*       feedback temporaire
bg-*          fond
fond-*        fond, alias francais accepte
decor-*       decoration
image-*       image contenu
gallery-*     galerie
icon-*        icone
titre-h1-*    titre niveau 1
titre-h2-*    titre niveau 2
titre-h3-*    titre niveau 3
texte-*       texte courant
label-*       libelle
link-label-*  texte de lien
placeholder-* placeholder visible
```

## Bons Reflexes

- Nommer une region ou section par son intention : `region-checkout-payment`,
  `section-aide`, `region-dashboard-main`.
- Nommer le type technique sur l'enfant : `form-payment`, `table-commandes`,
  `accordion-aide-01`.
- Garder les identites d'items stables : `card-product-01` doit representer le
  meme produit ou le meme slot logique sur toutes les largeurs.
- Garder le texte visible comme contenu publie. La semantique doit venir du nom
  de calque, pas de prefixes visibles dans le texte.
- Nommer les elements decoratifs avec `decor-*`, `bg-*` ou `fond-*`, surtout
  quand ils debordent volontairement.

## Anti-Patterns

Eviter les noms trop vagues :

```text
Frame 123
Group 7
Rectangle 91
zone
bloc
content
```

Eviter les sections qui decrivent seulement le composant :

```text
section-formulaire
section-table
section-modal
```

Preferer :

```text
section-contact
  form-contact

region-orders
  table-orders

modal-confirm-delete
```

Eviter de changer le nom d'un meme bloc entre breakpoints :

```text
section-embedded
section-input-output
section-embedded-infos
```

Preferer un nom stable :

```text
section-input-output
```

## Regle Courte

```text
page = source responsive
region = zone fonctionnelle
section = intention de contenu/metier
enfant = type de composant
texte visible = contenu publie
nom du calque = semantique
```



