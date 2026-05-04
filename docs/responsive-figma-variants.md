# Responsive Figma Variants

Kit de variantes pret a recopier dans Figma pour tester la conversion responsive multi-pages.

Voir aussi :
- [cahier-des-charges-responsive.md](/c:/dev/figma2hugo/docs/cahier-des-charges-responsive.md)

## Regles de base

- une page par largeur
- meme nom de page avec suffixe numerique
- memes noms de layers pour les items qui doivent matcher
- les items presents seulement a une largeur plus petite ont un nom distinct
- si le contenu change vraiment, dupliquer l'item au lieu de reutiliser exactement le meme nom
- pas de resize automatique cote moteur : les variantes sont preparees a la main dans Figma

## Largeurs recommandees

- `1920`
- `1280`
- `768`
- `390`

## Famille recommandee pour les tests

- `page-crash-test-1920`
- `page-crash-test-1280`
- `page-crash-test-768`
- `page-crash-test-390`

## Regles assets / bandeaux

- pour les grands bandeaux ou fonds visuels complexes, preferer un `png` ou `jpg` a la bonne taille finale
- eviter les `svg` composites pour les grands fonds masques, bandeaux obliques ou assemblages photo + formes
- separer les roles quand ils sont differents :
  - `bg-*` pour le fond principal
  - `image-*` pour une image de contenu
  - `logo-*` pour un logo isole
  - `decor-*` pour les decors flottants
- si un footer contact combine photo de fond et logo de droite, les separer en deux entites

Exemple recommande :

```text
footer-bandeau-contact
  bg-contact-photo
  image-contact-robot
  image-contact-logo-droite
  contact-illu
  formulaire-contact-post
```

## Nomenclature recommandee

- pages :
  - `page-accueil-1920`
  - `page-accueil-1280`
  - `page-accueil-768`
  - `page-accueil-390`
- sections :
  - `section-hero`
  - `section-accompagnement`
  - `section-embedded`
  - `section-valeurs`
  - `section-contact-moi`
  - `footer`
- textes :
  - `titre-h1-*`
  - `titre-h2-*`
  - `titre-h3-*`
  - `titre-h4-*`
  - `texte-*`
  - `label-*`
- actions :
  - `button-*`
  - `bg-button-*`
  - `texte-button-*`
- formulaires :
  - `formulaire-*`
  - `input-*`
  - `zone-*`
  - `placeholder-*`
  - `option-*`
  - `action-*`

## Desktop 1920

```text
page-crash-test-1920
  section-hero
    bg-hero
    titre-h1-hero
    texte-hero
    image-hero
    decor-hero-1
    decor-hero-2
    decor-hero-3

  section-accompagnement
    titre-h2-accompagnement
    card-prestation-1
      titre-h3-prestation-1
      texte-prestation-1
      texte-prestation-1-details
    card-prestation-2
      titre-h3-prestation-2
      texte-prestation-2
      texte-prestation-2-details
    button-accompagnement
      bg-button-accompagnement
      texte-button-accompagnement

  section-bandeau-cta
    bg-bandeau-cta
    image-bandeau-cta-gauche
    texte-bandeau-cta
    texte-bandeau-cta-details
    decor-bandeau-cta-1
    decor-bandeau-cta-2

  section-embedded
    logo-embedded
    col-embedded-decouvrez
      titre-h2-embedded-decouvrez
      texte-embedded-decouvrez
      button-labo
        bg-button-labo
        texte-button-labo
    col-embedded-financez
      titre-h2-embedded-financez
      texte-embedded-financez
      image-cir

  section-valeurs
    bg-valeurs
    card-valeur-idees
      image-valeur-idees
      label-valeur-idees
    card-valeur-plus
      image-valeur-plus
    card-valeur-expertises
      image-valeur-expertises
      label-valeur-expertises
    card-valeur-equals
      image-valeur-equals
    card-valeur-aventure
      image-valeur-aventure
      label-valeur-aventure

  section-contact-moi
    image-contact-moi
    titre-h2-contact-moi
    texte-contact-telephone
    texte-contact-mail
    button-mon-cv
      bg-button-mon-cv
      texte-button-mon-cv
    col-contact-moi-gauche
      titre-h3-contact-moi-gauche
      texte-contact-moi-gauche
      texte-contact-moi-gauche-details
    col-contact-moi-droite
      texte-contact-moi-droite
      titre-h4-contact-moi-droite
      texte-contact-moi-droite-details
    decor-contact-moi-1
    decor-contact-moi-2

  footer
    bg-footer
    footer-bandeau-contact
      bg-contact-photo
      image-contact-robot
      image-contact-logo-droite
      contact-illu
      formulaire-contact-post
        bg-contact-formulaire
        input-nom-prenom-required
          zone-nom-prenom
          placeholder-nom-prenom
        input-societe
          zone-societe
          placeholder-societe
        ligne-contact
          input-telephone-required
            zone-telephone
            placeholder-telephone
          input-mail-required
            zone-mail
            placeholder-mail
        input-select-demande-required
          zone-demande
          option-choix-demande-selected
          option-demande-audit
          option-demande-expertise
          option-demande-formation
        input-message-required
          zone-message
          placeholder-message
        action-contact
        button-envoyer
          bg-button-envoyer
          texte-button-envoyer
    footer-text
```

## Laptop 1280

```text
page-crash-test-1280
  section-hero
    bg-hero
    titre-h1-hero
    texte-hero
    image-hero
    decor-hero-1
    decor-hero-2
    decor-hero-3

  section-accompagnement
    titre-h2-accompagnement
    card-prestation-1
      titre-h3-prestation-1
      texte-prestation-1
      texte-prestation-1-details
    card-prestation-2
      titre-h3-prestation-2
      texte-prestation-2
      texte-prestation-2-details
    button-accompagnement
      bg-button-accompagnement
      texte-button-accompagnement

  section-bandeau-cta
    bg-bandeau-cta
    image-bandeau-cta-gauche
    texte-bandeau-cta
    texte-bandeau-cta-details
    decor-bandeau-cta-1
    decor-bandeau-cta-2

  section-embedded
    logo-embedded
    col-embedded-decouvrez
      titre-h2-embedded-decouvrez
      texte-embedded-decouvrez
      button-labo
        bg-button-labo
        texte-button-labo
    col-embedded-financez
      titre-h2-embedded-financez
      texte-embedded-financez
      image-cir

  section-valeurs
    bg-valeurs
    card-valeur-idees
      image-valeur-idees
      label-valeur-idees
    card-valeur-plus
      image-valeur-plus
    card-valeur-expertises
      image-valeur-expertises
      label-valeur-expertises
    card-valeur-equals
      image-valeur-equals
    card-valeur-aventure
      image-valeur-aventure
      label-valeur-aventure

  section-contact-moi
    image-contact-moi
    titre-h2-contact-moi
    texte-contact-telephone
    texte-contact-mail
    button-mon-cv
      bg-button-mon-cv
      texte-button-mon-cv
    col-contact-moi-gauche
      titre-h3-contact-moi-gauche
      texte-contact-moi-gauche
      texte-contact-moi-gauche-details
    col-contact-moi-droite
      texte-contact-moi-droite
      titre-h4-contact-moi-droite
      texte-contact-moi-droite-details
    decor-contact-moi-1
    decor-contact-moi-2

  footer
    bg-footer
    footer-bandeau-contact
      bg-contact-photo
      image-contact-robot
      image-contact-logo-droite
      contact-illu
      formulaire-contact-post
        bg-contact-formulaire
        input-nom-prenom-required
          zone-nom-prenom
          placeholder-nom-prenom
        input-societe
          zone-societe
          placeholder-societe
        ligne-contact
          input-telephone-required
            zone-telephone
            placeholder-telephone
          input-mail-required
            zone-mail
            placeholder-mail
        input-select-demande-required
          zone-demande
          option-choix-demande-selected
          option-demande-audit
          option-demande-expertise
          option-demande-formation
        input-message-required
          zone-message
          placeholder-message
        action-contact
        button-envoyer
          bg-button-envoyer
          texte-button-envoyer
```

## Tablet 768

```text
page-crash-test-768
  section-hero
    bg-hero
    titre-h1-hero
    texte-hero
    image-hero
    decor-hero-1
    decor-hero-2

  section-accompagnement
    titre-h2-accompagnement
    card-prestation-1
      titre-h3-prestation-1
      texte-prestation-1
      texte-prestation-1-details
    card-prestation-2
      titre-h3-prestation-2
      texte-prestation-2
      texte-prestation-2-details
    button-accompagnement
      bg-button-accompagnement
      texte-button-accompagnement

  section-bandeau-cta
    bg-bandeau-cta
    image-bandeau-cta-gauche
    texte-bandeau-cta
    texte-bandeau-cta-details

  section-embedded
    logo-embedded
    col-embedded-decouvrez
      titre-h2-embedded-decouvrez
      texte-embedded-decouvrez
      button-labo
        bg-button-labo
        texte-button-labo
    col-embedded-financez
      titre-h2-embedded-financez
      texte-embedded-financez
      image-cir

  section-valeurs
    bg-valeurs
    card-valeur-idees
      image-valeur-idees
      label-valeur-idees
    card-valeur-plus
      image-valeur-plus
    card-valeur-expertises
      image-valeur-expertises
      label-valeur-expertises
    card-valeur-equals
      image-valeur-equals
    card-valeur-aventure
      image-valeur-aventure
      label-valeur-aventure

  section-contact-moi
    image-contact-moi
    titre-h2-contact-moi
    texte-contact-telephone
    texte-contact-mail
    button-mon-cv
      bg-button-mon-cv
      texte-button-mon-cv
    col-contact-moi-gauche
      titre-h3-contact-moi-gauche
      texte-contact-moi-gauche
      texte-contact-moi-gauche-details
    col-contact-moi-droite
      texte-contact-moi-droite
      titre-h4-contact-moi-droite
      texte-contact-moi-droite-details

  footer
    bg-footer
    footer-bandeau-contact
      bg-contact-photo
      image-contact-robot
      image-contact-logo-droite
      contact-illu
      formulaire-contact-post
        bg-contact-formulaire
        input-nom-prenom-required
          zone-nom-prenom
          placeholder-nom-prenom
        input-societe
          zone-societe
          placeholder-societe
        input-telephone-required
          zone-telephone
          placeholder-telephone
        input-mail-required
          zone-mail
          placeholder-mail
        input-select-demande-required
          zone-demande
          option-choix-demande-selected
          option-demande-audit
          option-demande-expertise
          option-demande-formation
        input-message-required
          zone-message
          placeholder-message
        action-contact
        button-envoyer
          bg-button-envoyer
          texte-button-envoyer
```

## Mobile 390

```text
page-crash-test-390
  section-hero
    bg-hero
    titre-h1-hero
    texte-hero
    image-hero
    hero-mobile-note
    decor-hero-1

  section-accompagnement
    titre-h2-accompagnement
    card-prestation-1
      titre-h3-prestation-1
      texte-prestation-1
      texte-prestation-1-details
    card-prestation-2
      titre-h3-prestation-2
      texte-prestation-2
      texte-prestation-2-details
    button-accompagnement
      bg-button-accompagnement
      texte-button-accompagnement

  section-bandeau-cta
    bg-bandeau-cta
    texte-bandeau-cta
    texte-bandeau-cta-details

  section-embedded
    logo-embedded
    col-embedded-decouvrez
      titre-h2-embedded-decouvrez
      texte-embedded-decouvrez
      button-labo
        bg-button-labo
        texte-button-labo
    col-embedded-financez
      titre-h2-embedded-financez
      texte-embedded-financez
      image-cir

  section-valeurs
    bg-valeurs
    card-valeur-idees
      image-valeur-idees
      label-valeur-idees
    card-valeur-plus
      image-valeur-plus
    card-valeur-expertises
      image-valeur-expertises
      label-valeur-expertises
    card-valeur-equals
      image-valeur-equals
    card-valeur-aventure
      image-valeur-aventure
      label-valeur-aventure

  section-contact-moi
    image-contact-moi
    titre-h2-contact-moi
    texte-contact-telephone
    texte-contact-mail
    button-mon-cv
      bg-button-mon-cv
      texte-button-mon-cv
    contact-moi-mobile-note
    col-contact-moi-gauche
      titre-h3-contact-moi-gauche
      texte-contact-moi-gauche
      texte-contact-moi-gauche-details
    col-contact-moi-droite
      texte-contact-moi-droite
      titre-h4-contact-moi-droite
      texte-contact-moi-droite-details

  footer
    bg-footer
    footer-bandeau-contact
      bg-contact-photo
      image-contact-robot
      image-contact-logo-droite
      contact-illu
      formulaire-contact-post
        bg-contact-formulaire
        input-nom-prenom-required
          zone-nom-prenom
          placeholder-nom-prenom
        input-societe
          zone-societe
          placeholder-societe
        input-telephone-required
          zone-telephone
          placeholder-telephone
        input-mail-required
          zone-mail
          placeholder-mail
        input-select-demande-required
          zone-demande
          option-choix-demande-selected
          option-demande-audit
          option-demande-expertise
          option-demande-formation
        input-message-required
          zone-message
          placeholder-message
        action-contact
        button-envoyer
          bg-button-envoyer
          texte-button-envoyer
```

## Notes de test

- Les pages doivent etre exportees/generes ensemble pour que la fusion responsive s'active.
- Les items qui doivent matcher doivent garder exactement le meme nom entre toutes les largeurs.
- Les items supplementaires doivent avoir un nom specifique :
  - `hero-mobile-note`
  - `contact-moi-mobile-note`
- Si un meme item change vraiment de texte ou d'image entre deux largeurs, il vaut mieux le dupliquer avec un nom specifique breakpoint.
- Pour les grands bandeaux et fonds complexes, preferer un `png` ou `jpg` a la bonne taille finale. Eviter les `svg` composites comme support principal.

## Variante minimale pour test rapide

Si vous voulez un test minimal avant la vraie page :

```text
page-smoke-test-1920
  section-hero
    titre-h1-hero
    texte-hero
    image-hero

page-smoke-test-390
  section-hero
    titre-h1-hero
    texte-hero
    image-hero
    hero-mobile-note
```
