# Figma Naming Conventions

Ce document rassemble la nomenclature recommandee pour que `figma2hugo` comprenne mieux les intentions de structure, de fond, de decor, d'interaction et de responsive.

## Principes generaux

- utiliser des noms simples, explicites et stables
- preferer les minuscules avec tirets: `section-hero`, `bg-button-envoyer`
- garder le meme nom pour le meme element logique entre variantes responsive
- si un element change vraiment de contenu ou de role, lui donner un autre nom
- separer le contenu, le fond et le decor plutot que tout melanger dans un seul groupe

## Pages et variantes

- une page par largeur
- meme famille de page avec suffixe numerique

Exemples:

- `page-accueil-1920`
- `page-accueil-1280`
- `page-accueil-768`
- `page-accueil-390`
- `page-prestation-1920`

## Sections et structure

Utiliser des noms de section explicites:

- `section-hero`
- `section-faq`
- `section-cas-clients`
- `section-contact`
- `footer`

Pour les sous-structures de layout:

- `row-*`
- `col-*`
- `ligne-*`
- `content-*`

## Textes

Utiliser des prefixes semantiques:

- `titre-h1-*`
- `titre-h2-*`
- `titre-h3-*`
- `titre-h4-*`
- `titre-h5-*`
- `titre-h6-*`
- `texte-*`
- `label-*`
- `link-label-*`
- `placeholder-*`

## Assets et roles visuels

Le moteur reconnait mieux les intentions si les assets sont nommes par role:

- `bg-*` pour un fond
- `fond-*` ou `background-*` fonctionnent aussi
- `image-*` pour une image de contenu
- `icon-*` ou `icone-*` pour une icone
- `logo-*` pour un logo
- `decor-*` pour un decor

Exemples:

- `bg-hero`
- `bg-button-envoyer`
- `image-card-projet-1`
- `icone-plus-1`
- `logo-embedded`
- `decor-hero-1`

## Buttons

Structure recommandee:

```text
button-envoyer
  bg-button-envoyer
  texte-button-envoyer
```

Autres exemples:

```text
button-mon-cv
  bg-button-mon-cv
  texte-button-mon-cv
```

```text
button-labo
  bg-button-labo
  texte-button-labo
```

## Accordion / FAQ

Structure recommandee:

```text
section-faq
  accordion-single-faq
    accordion-item-1-open
      accordion-trigger-1
        bg-accordion-trigger-1
        icone-plus-1
        texte-question-1
      accordion-panel-1
        texte-reponse-1
    accordion-item-2-closed
      accordion-trigger-2
        bg-accordion-trigger-2
        icone-plus-2
        texte-question-2
      accordion-panel-2
        texte-reponse-2
```

Important:

- le conteneur du trigger doit s'appeler `accordion-trigger-*`
- le fond du trigger doit etre un enfant nomme `bg-*`, par exemple `bg-accordion-trigger-1`
- le fond du panel peut suivre la meme logique si besoin: `bg-accordion-panel-1`
- l'icone doit rester distincte: `icone-plus-1`
- le texte doit rester distinct: `texte-question-1`, `texte-reponse-1`

Etat des items:

- `accordion-item-1-open`
- `accordion-item-2-closed`

Le suffixe `open` / `closed` aide le moteur a initialiser l'etat de depart.

## Cards et matrices de liens

Structure recommandee:

```text
link-grid-cas-clients
  link-row-1
    href-card-projet-1-external
      bg-card-projet-1
      image-card-projet-1
      texte-projet-1
      link-label-projet-1
    href-card-projet-2-external
      bg-card-projet-2
      image-card-projet-2
      texte-projet-2
      link-label-projet-2
```

Points utiles:

- `href-card-*` pour une carte cliquable
- `link-grid-*` pour la matrice globale
- `bg-card-*` pour le fond de la carte
- `image-card-*` pour le media principal

## Formulaires

Structure recommandee:

```text
formulaire-contact-post
  bg-contact-formulaire
  input-nom-prenom-required
    zone-nom-prenom
    placeholder-nom-prenom
  input-mail-required
    zone-mail
    placeholder-mail
  input-message-required
    zone-message
    placeholder-message
  button-envoyer
    bg-button-envoyer
    texte-button-envoyer
```

Prefixes utiles:

- `formulaire-*`
- `input-*`
- `zone-*`
- `placeholder-*`
- `option-*`
- `action-*`

## Responsive

Pour les variantes responsive:

- garder les memes noms pour les memes elements logiques
- ne pas renommer un item juste parce qu'il change de position
- si un element n'existe qu'a une largeur, lui donner un nom distinct
- si le contenu textuel change vraiment, dupliquer l'element au lieu d'utiliser exactement le meme nom

Exemple:

- `page-prestation-1920`
- `page-prestation-1280`
- `page-prestation-768`
- `page-prestation-390`

## En cas de doute

Si tu hesites sur un nom:

- decrire le role avant l'apparence
- privilegier `bg-*`, `image-*`, `decor-*`, `texte-*`, `button-*`, `accordion-*`
- eviter les noms generiques comme `frame-12`, `rectangle-8`, `group-4` quand ils portent une intention fonctionnelle

Voir aussi:

- [README.md](../README.md)
- [responsive-figma-variants.md](./responsive-figma-variants.md)
- [cahier-des-charges-responsive.md](./cahier-des-charges-responsive.md)
