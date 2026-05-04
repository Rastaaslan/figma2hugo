# Cahier Des Charges Responsive

## Objectif

Permettre a `figma2hugo` de fusionner plusieurs pages Figma d'une meme famille en une seule page web responsive, sans resize automatique cote moteur.

Le responsive est pilote par :
- une page Figma par largeur
- un nom de page partage
- des noms de layers stables

## Perimetre

Le systeme vise :
- une base HTML issue de la plus grande largeur
- des overrides CSS par breakpoint
- des items additionnels autorises sur les petites largeurs
- aucune transformation geometrique automatique des maquettes

Le systeme ne vise pas :
- un resize ou une adaptation intelligente des positions
- une reinterpretation automatique d'une seule maquette desktop en responsive complet

## Convention De Nom Des Pages

Chaque variante doit suivre :

```text
page-<slug>-<width>
```

Exemples :
- `page-accueil-1920`
- `page-accueil-1280`
- `page-accueil-768`
- `page-accueil-390`

La page finale fusionnee est :
- `page-accueil`

## Breakpoints Recommandes

- `1920`
- `1280`
- `768`
- `390`

## Regle De Fusion

- la variante la plus large fournit le HTML de base
- les variantes plus petites produisent des `@media (max-width: ...)`
- les items de meme nom sont consideres comme le meme element si leur parent logique est stable
- les items presents seulement sur une largeur plus petite sont ajoutes au HTML fusionne, caches par defaut, puis affiches au bon breakpoint

## Regle De Matching Des Layers

Pour matcher entre largeurs, un item doit garder :
- le meme nom
- le meme role
- un parent logique equivalent

Exemple :

```text
section-hero
  titre-h1-hero
  texte-hero
  image-hero
```

Le moteur considere qu'il s'agit du meme bloc entre `1920`, `1280`, `768`, `390`.

## Items Specifiques A Une Largeur

Si un item n'existe que sur une petite largeur, il doit avoir un nom distinct.

Exemples :
- `hero-mobile-note`
- `contact-moi-mobile-note`
- `button-cta-mobile`

Comportement attendu :
- l'item est ajoute au HTML fusionne
- il est cache par defaut
- il est affiche au breakpoint concerne

## Changement De Contenu

Si un item change reellement entre deux largeurs sur un meme nom :
- texte completement different
- image differente
- nature de controle differente

alors il ne doit pas etre considere comme le meme item.

Regle :
- dupliquer l'element
- lui donner un nom specifique au breakpoint

## Regles De Nomenclature

### Pages

- `page-*`

### Sections

- `section-*`
- `footer`
- `header`

### Textes

- `titre-h1-*`
- `titre-h2-*`
- `titre-h3-*`
- `titre-h4-*`
- `texte-*`
- `label-*`

### Assets

- `bg-*`
- `image-*`
- `logo-*`
- `decor-*`

### Actions

- `button-*`
- `bg-button-*`
- `texte-button-*`

### Formulaires

- `formulaire-*`
- `input-*`
- `zone-*`
- `placeholder-*`
- `option-*`
- `action-*`

## Regles Assets / Fonds

- les grands fonds complexes doivent etre fournis en `png` ou `jpg` a la bonne taille finale
- eviter les `svg` composites pour les grands bandeaux visuels ou fonds masques
- separer les roles d'assets si leurs comportements different

Exemple recommande :

```text
footer-bandeau-contact
  bg-contact-photo
  image-contact-robot
  image-contact-logo-droite
  contact-illu
  formulaire-contact-post
```

## Contraintes De Production

- aucune adaptation automatique des dimensions de la maquette
- le travail de mise en page responsive est fait a la main dans Figma
- le moteur se contente de fusionner des variantes coherentes

## Critere D'Acceptation

Le responsive est considere conforme si :
- la page fusionnee finale n'est generee qu'une seule fois par famille
- les breakpoints correspondent aux largeurs suffixees
- les items partages gardent leur contenu et leur role
- les items additionnels apparaissent seulement au bon breakpoint
- aucun warning critique n'indique un conflit de texte/image sur un meme item partage

## Workflow Recommande

1. construire la page desktop `1920`
2. dupliquer en `1280`, `768`, `390`
3. adapter la mise en page a la main dans Figma
4. garder les noms stables pour les items communs
5. nommer distinctement les items specifiques a une largeur
6. exporter/generer toutes les variantes ensemble
7. verifier la fusion CSS et les warnings
