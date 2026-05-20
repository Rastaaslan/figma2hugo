# Contrat Figma Authoring pipeline

Ce contrat decrit la forme attendue dans Figma pour que le pipeline puisse
generer un site Hugo stable, reproductible et testable. Il complete la
nomenclature detaillee de `docs/figma-naming-conventions.md`.

Documents pratiques :

- `docs/figma-page-architecture-reference.md` : architecture Figma generique
  avec regions, sections, composants, overlays et variantes responsive.
- `docs/notice-utilisateur-technique.md` : notice utilisateur et technique
  pour generation, baselines, contrats responsive et release gate.

## Principe

Figma est la source de verite pour le contenu, la structure, les breakpoints,
les noms de calques et l'intention visuelle. Le pipeline ne doit pas deviner
une intention metier quand Figma peut la porter explicitement.

Seule exception : les composants web interactifs doivent rester utilisables
dans le navigateur. Un formulaire, un accordion, un carousel, une link card ou
un controle equivalent peut donc recevoir un ajustement HTML/CSS borne quand la
geometrie Figma serait fidele mais inutilisable, inaccessible ou non testable.
Ces ajustements ne changent pas le contenu et sont reportes comme signaux de
revue.

Les noms de calques donnent l'intention, les textes visibles restent le contenu
de maquette, et les dimensions de page donnent les breakpoints.

Important : le contenu visible n'est pas nettoye automatiquement. Si une
maquette contient `Title - Mentions legales` ou `H3 - Informations generales`,
ce texte est considere volontaire. Le role semantique doit venir du nom du
calque, par exemple `titre-h1-mentions-legales` ou
`titre-h3-informations-generales`.

## Pages

Les frames de page suivent `page-<slug>-<width>` :

```text
page-mentions-legales-1920
page-mentions-legales-834
page-mentions-legales-402
```

Les largeurs supportees doivent etre exactes pour les boards concernes :

- desktop : `1920`
- tablette : `834`
- mobile : `402`

Le frame principal doit commencer a `x = 0` et avoir la largeur exacte du
board. Les fonds ou decors qui depassent volontairement ne doivent pas devenir
le frame principal : ils doivent etre nommes `decor-*`, `bg-*` ou `fond-*`.

Seul le frame page porte la largeur. Les enfants ne doivent pas recevoir de
suffixes comme `-w834` ou `-w402`; si le moteur a besoin d'identites CSS
specifiques, il les genere lui-meme.

## Identite Stable

Un element qui represente le meme contenu ou le meme role garde le meme nom
entre desktop, tablette et mobile, meme s'il change de position.

```text
section-contact
  formulaire-contact
  titre-h2-contact
```

Un element propre a une dimension prend un nom specifique :

```text
texte-contact-mobile-intro
button-cta-mobile
decor-hero-tablette-01
```

Une section peut exister seulement sur certains breakpoints si la mise en forme
le justifie. Dans ce cas, elle doit quand meme porter un nom d'intention stable
si elle represente le meme bloc metier.

Pour une famille responsive, un meme bloc metier ne doit pas changer de nom
selon la largeur. Par exemple, le bloc Inputs/Livrables/Devis ne doit pas
s'appeler successivement `section-embedded`, `section-input-output` puis
`section-embedded-infos` si c'est le meme contenu. Utiliser un nom stable,
comme `section-input-output`, puis laisser la position et la composition varier.

Si un contenu est volontairement absent sur un breakpoint, le choix doit etre
explicite dans la maquette ou dans le contrat de page. Le pipeline le garde
comme signal de revue, pas comme erreur de rendu.

Le rapport responsive expose les signaux de contrat suivants :

- `contractRule: stable-responsive-content` : un bloc present a toutes les
  largeurs garde la meme signature de contenu. Action attendue :
  `align-copy-or-declare-intentional-variant`.
- `contractRule: stable-breakpoint-presence` : un bloc metier partage garde une
  presence stable sur les breakpoints, sauf variante intentionnelle. Action
  attendue : `add-missing-node-or-declare-breakpoint-only`.
- `contractRule: stable-collection-order` : les collections gardent la meme
  identite de contenu ; un changement d'ordre doit etre declare comme variante
  de carousel/grille. Action attendue :
  `normalize-order-or-declare-carousel-variant`.

Chaque signal porte aussi `nodeRole` et `contractRisk` pour trier la revue :
`footer`, `hero`, `case-studies`, `service-section`, `embedded-content`, `faq`
ou le type structurel generique. Ces champs servent a guider la correction
Figma ; ils ne declenchent aucune reparation runtime dans Hugo.

## Declarations responsive versionnees

Quand une variante responsive est intentionnelle, elle doit etre declaree dans
un contrat JSON passe au build avec `--responsive-contract`. Le contrat ne
change pas le HTML, le CSS ou les fichiers Hugo generes ; il change seulement
la classification de revue de `actionable-review` vers `accepted-contract`.

Exemple :

```json
{
  "version": 1,
  "responsiveContracts": [
    {
      "family": "page-prestation-2",
      "code": "content-conflict",
      "key": "section:section-hero",
      "differenceKind": "content-delta",
      "contractRule": "stable-responsive-content",
      "presentWidths": [402, 834, 1920],
      "decision": "intentional-content-variant",
      "rationale": "Hero messaging is intentionally adapted by breakpoint.",
      "owner": "figma-contract"
    }
  ]
}
```

Le matching est volontairement strict : `family`, `code`, `key`,
`differenceKind`, `contractRule` et `presentWidths` doivent correspondre au
signal courant. `missingWidths` peut etre ajoute pour les blocs
`breakpoint-only`. Avec `scripts/release_gate.py --responsive-contract`, le
gate refuse les declarations invalides ou qui ne matchent plus aucun signal
courant, afin d'eviter qu'une ancienne acceptation masque une derive Figma.

Pour eviter des chemins specifiques a un projet, le meme contrat peut aussi
etre promu et resolu par `sourceIdentity.projectId` :

```powershell
python -m figma2hugo.cli promote-review-baseline site --baseline-root baselines\review\pipeline\projects --label first-approved
python scripts\release_gate.py <site-dir> --page-file <pages.txt> --responsive-contract-root baselines\review\pipeline\projects
```

Cette baseline reste une validation de rendu/review, pas une nouvelle source de
verite qui remplace Figma. Si Figma change intentionnellement, il faut
regenerer, relire le rendu, puis promouvoir un nouveau snapshot.

## Sections

Les sections structurelles utilisent `section-*` :

```text
section-hero
section-contenu-legal
section-cas-clients
section-faq
section-contact
footer
```

La section ou region doit nommer l'intention metier du bloc, pas seulement le
type technique du composant qu'elle contient. Les exemples ci-dessous ne sont
pas reserves aux sites vitrines : la convention doit rester valable pour une
page marketing, une app, un dashboard, un tunnel d'achat, une fiche produit ou
un back-office.

Exemples :

```text
section-contact
  formulaire-contact

section-demande-de-devis
  formulaire-devis

section-faq-prestations
  accordion-prestations-01

section-faq-tarifs
  accordion-tarifs-01

region-dashboard-main
  toolbar-filtres
  table-commandes
  pagination-commandes

region-product-detail
  gallery-product
  panel-purchase
  form-options

region-checkout-payment
  form-payment
  summary-order

region-settings-profile
  form-profile
  panel-security
```

a des sections trop generiques comme `section-formulaire` ou `section-faq` si
la page peut contenir plusieurs formulaires ou plusieurs FAQ. Le principe est :
`section-*` ou `region-*` porte l'intention metier, tandis que
`formulaire-*`, `form-*`, `accordion-*`, `card-*`, `table-*`, `toolbar-*`,
`panel-*`, `modal-*`, `drawer-*`, `nav-*`, `cta-*` portent le type de
composant.

Les noms de position restent acceptables pour des morceaux purement visuels
d'un meme bandeau, par exemple `bandeau-gauche` ou `bandeau-droite`, mais les
blocs fonctionnels doivent preferer l'intention :

```text
section-cta-accompagnement
section-cta-cas-clients
cta-accompagnement-bg
cta-accompagnement-title
cta-accompagnement-body
```

## Textes

Les prefixes de texte portent la semantique :

```text
titre-h1-*
titre-h2-*
titre-h3-*
texte-*
label-*
link-label-*
placeholder-*
```

Le texte visible reste une donnee publiee. La convention ne demande pas de
retirer les prefixes humains de la maquette si ces prefixes font partie du
texte voulu dans Figma.

Ne pas utiliser le texte visible pour porter la semantique responsive. Par
exemple, `Titre H1` sur desktop et `Titre H2` sur mobile sont deux contenus
publies differents. Le niveau doit etre dans le nom de calque
(`titre-h1-*`, `titre-h2-*`), tandis que le texte visible reste la copie
finale.

## Cartes Et Collections

Une carte repetee garde son identite metier entre breakpoints :

```text
case-card-01
  case-card-01-bg
  case-card-01-image
  case-card-01-title
  case-card-01-link
```

La numerotation est correcte si `case-card-01` designe toujours la meme carte.
L'ordre peut changer en mobile ou tablette. Le probleme apparait seulement si
la meme identite designe un contenu different selon la largeur, ou si plusieurs
cartes soeurs reutilisent le meme nom.

Quand une collection change d'ordre ou passe en carrousel sur mobile, conserver
les memes identites d'items. Si le nombre d'items change selon la largeur, le
signaler comme variante responsive voulue plutot que reutiliser les memes noms
pour des contenus differents.

## Assets

Nommer le role avant l'apparence :

```text
bg-hero
fond-contact
image-case-card-01
logo-client
decor-hero-01
foreground-reflet-card
icon-plus-01
```

Les fonds couvrants, formes decoratives et images de contenu doivent rester
separes. Un groupe opaque qui melange texte, fond et decor rend le responsive
plus fragile.
Les elements explicitement nommes `foreground-*`, `fg-*`, `avant-plan-*` ou
`premier-plan-*` sont traites comme une couche d'avant-plan et passent devant
les assets et decors.

## Formulaires

Structure recommandee :

```text
formulaire-contact
  input-nom-prenom
    placeholder-nom-prenom
  input-societe
    placeholder-societe
  input-telephone
    placeholder-telephone
  input-email
    placeholder-email
  input-sujet
    placeholder-sujet
  input-message
    placeholder-message
  button-envoyer
    bg-button-envoyer
    texte-button-envoyer
```

## Critere De Promotion

Une maquette est prete pour le pipeline quand :

- les pages suivent `page-<slug>-<width>`
- les frames principales sont snappees a `x = 0` et aux largeurs exactes
- les sections communes gardent des noms stables
- les elements propres a une dimension portent des noms specifiques
- les collections gardent une identite metier stable
- les roles `bg-*`, `image-*`, `decor-*`, `texte-*` sont separes
- le gate pipeline passe sans issue bloquante

Commande de gate recommandee :

```bash
python scripts/release_gate.py <site-dir> --page-file <pages.txt> --responsive-contract baselines/review/pipeline/real-pages-responsive-contract.json
```

Le rapport visuel est disponible dans le dossier smoke via `review.html`.



