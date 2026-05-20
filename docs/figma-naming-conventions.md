# Figma Naming Conventions

Ce document rassemble la nomenclature recommandee pour que `figma2hugo` comprenne mieux les intentions de structure, de fond, de decor et d'interaction.

## Principes generaux

- utiliser des noms simples, explicites et stables
- preferer les minuscules avec tirets: `section-hero`, `bg-button-envoyer`
- si un element change vraiment de contenu ou de role, lui donner un autre nom
- separer le contenu, le fond et le decor plutot que tout melanger dans un seul groupe

## Pages

Exemples:

- `page-accueil`
- `page-prestation`
- `page-contact`

Pour une famille responsive multi-largeurs, ajouter la largeur en suffixe et
garder le meme slug de famille :

- `page-accueil-1920`
- `page-accueil-1280`
- `page-accueil-834`
- `page-accueil-402`

La partie avant la largeur est l'identifiant de famille. `page-accueil-1920`
et `page-home-402` ne seront donc pas traites comme deux variantes de la meme
page.

Seul le frame page porte la largeur. Eviter les suffixes de breakpoint dans les
enfants Figma (`-w834`, `-w402`). Quand le moteur a besoin d'identites CSS
specifiques a un breakpoint, il les genere lui-meme et remplace le suffixe
precedent au lieu de l'empiler.

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

Les noms de position (`bandeau-gauche`, `bandeau-droite-*`) sont acceptables
quand ils decrivent un morceau purement visuel d'un meme bandeau. Pour une
intention fonctionnelle ou reutilisable, preferer un nom metier stable:

- `section-cta-accompagnement`
- `section-cta-cas-clients`
- `cta-accompagnement-bg`
- `cta-accompagnement-title`
- `cta-accompagnement-body`

Pour une famille responsive, garder le meme nom pour le meme bloc metier entre
largeurs. Eviter de faire varier le nom selon le format si le contenu reste le
meme:

```text
section-input-output
section-input-output
section-input-output
```

Plutot que:

```text
section-embedded
section-input-output
section-embedded-infos
```

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

Le texte visible reste le contenu de maquette. Le moteur ne retire pas
automatiquement `Title -`, `H1 -` ou `H3 -` quand ces mots sont presents dans
Figma. La semantique vient du nom du calque, pas d'un nettoyage implicite du
texte publie.

Le niveau de titre doit donc etre dans le nom du calque, pas dans le texte
visible. `titre-h1-prestation` peut afficher `Formations`; il ne doit pas avoir
besoin d'afficher `Titre H1 - Formations`.

## Assets et roles visuels

Le moteur reconnait mieux les intentions si les assets sont nommes par role:

- `bg-*` pour un fond
- `fond-*` ou `background-*` fonctionnent aussi
- `image-*` pour une image de contenu
- `icon-*` ou `icone-*` pour une icone
- `logo-*` pour un logo
- `decor-*` pour un decor
- `foreground-*`, `fg-*`, `avant-plan-*` ou `premier-plan-*` pour un element qui
  doit passer devant les assets et decors

Exemples:

- `bg-hero`
- `bg-button-envoyer`
- `image-card-projet-1`
- `icone-plus-1`
- `logo-embedded`
- `decor-hero-1`
- `foreground-reflet-card`

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

La numerotation est valide si elle identifie le meme item metier entre
breakpoints. Par exemple `projet-1` peut changer de position en mobile, mais il
doit rester le meme projet. Pour une convention plus explicite:

```text
case-card-01
  case-card-01-bg
  case-card-01-image
  case-card-01-title
  case-card-01-link
```

Le probleme apparait seulement si `projet-4` designe une carte differente selon
la largeur, ou si plusieurs cartes soeurs reutilisent la meme identite.

Si la collection change d'ordre en mobile, garder les memes numeros ou IDs
metier. Si des cartes disparaissent volontairement, documenter cette variante
plutot que reutiliser les noms pour d'autres cartes.

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

## En cas de doute

Si tu hesites sur un nom:

- decrire le role avant l'apparence
- privilegier `bg-*`, `image-*`, `decor-*`, `texte-*`, `button-*`, `accordion-*`
- eviter les noms generiques comme `frame-12`, `rectangle-8`, `group-4` quand ils portent une intention fonctionnelle

## Convention responsive operationnelle

Objectif: limiter les bugs de merge responsive avant generation Hugo.

### Ce qui doit rester stable entre largeurs

Garder exactement le meme nom quand l'element represente le meme contenu ou le
meme role :

```text
page-prestation-1920
  section-hero
    titre-h1-hero
    texte-hero
    image-hero

page-prestation-402
  section-hero
    titre-h1-hero
    texte-hero
    image-hero
```

Cela vaut surtout pour :

- sections structurelles : `section-hero`, `section-contact`, `footer`
- textes conserves : `titre-h1-*`, `titre-h2-*`, `texte-*`, `label-*`
- images de contenu conservees : `image-*`, `logo-*`
- composants repetes : `card-*`, `href-card-*`, `accordion-item-*`, `input-*`

### Ce qui doit changer de nom

Donner un nom distinct quand l'element existe seulement a un breakpoint ou
quand son role/contenu change vraiment :

- `hero-mobile-note`
- `button-cta-mobile`
- `image-hero-mobile`
- `texte-contact-mobile-intro`

Ne pas reutiliser `texte-hero` pour un texte mobile qui n'a plus le meme
contenu. Le rapport le classera comme `text-content-change` et l'audit manuel
devra trancher.

### Freres avec le meme nom

Eviter deux enfants de meme nom sous le meme parent, sauf collection repetitive
claire :

```text
section-features
  card-feature-1
  card-feature-2
  card-feature-3
```

Preferer cela a :

```text
section-features
  card-feature
  card-feature
  card-feature
```

Si le rapport mentionne `duplicate-sibling-token`, renommer ou numeroter les
freres ambigus. Si le rapport mentionne `repeated-component-token`, verifier que
le groupe est bien une collection volontaire.

### Sections et intentions de layout

Une section partagee doit garder le meme role entre breakpoints. Eviter de
faire matcher un `section-hero` desktop avec un bloc mobile devenu
`section-intro-contact` ou une structure sans equivalent.

Les variantes proches peuvent rester matchables si le nom reste contenu et
explicite, par exemple :

- `section-hero`
- `section-hero-main`

Mais une section vraiment nouvelle doit prendre un nom specifique :

- `section-hero-mobile-note`
- `section-contact-mobile-shortcut`

Si le rapport pipeline remonte une revue responsive de type section manquante ou
intention divergente, aligner les noms de sections manquantes, normaliser le
pattern Figma entre largeurs ou separer explicitement les variantes.

### Fonds, decors et contenu

Ne pas melanger un fond/decor avec le contenu principal dans un groupe opaque.
Nommer les roles separement :

```text
section-hero
  bg-hero
  decor-hero-1
  titre-h1-hero
  texte-hero
  image-hero
```

Si le rapport pipeline remonte un melange decor/contenu, sortir les layers `bg-*`,
`fond-*`, `background-*` ou `decor-*` du flux de contenu et les garder comme
enfants clairement identifies de la section.

### Textes longs

Nommer les textes par role et eviter les longs paragraphes dans des boites
fixes et trop etroites :

- `texte-intro`
- `texte-description`
- `texte-card-projet-1`

Si le rapport pipeline remonte un texte long trop contraint, autoriser le texte a
grandir en hauteur dans Figma ou le placer dans une structure `stack`/colonne
plus explicite.

### Checklist avant export

- Les pages suivent `page-<slug>-<width>`.
- Les sections communes ont les memes noms ou des alias tres proches.
- Les elements communs gardent le meme nom entre largeurs.
- Les elements propres au mobile/tablet ont un nom specifique.
- Aucun parent ne contient plusieurs freres ambigus avec le meme nom.
- Les roles `bg-*`, `image-*`, `decor-*`, `texte-*` sont separes.
- Les longs textes ne sont pas bloques dans une petite boite fixe.
- Apres generation, verifier `report.json` et le rapport `visual-smoke`.

Voir aussi:

- [README.md](../README.md)
- [figma-authoring-contract.md](./figma-authoring-contract.md)
