# Responsive Memory And Progress

Derniere mise a jour : 2026-05-05

## Role De Ce Fichier

Ce document sert de memoire de chantier pour le responsive multi-variantes.
Il doit permettre de savoir, a tout moment :

- ce qui est deja implemente
- ce qui a ete decide
- ce qui reste a faire
- ou sont les garde-fous de regression
- quels fichiers portent chaque partie du systeme

Note :
- ce fichier sert maintenant aussi de suivi transverse pour les chantiers UI, factorisation, nettoyage et optimisation lies au convertisseur

## Cible Produit

La cible retenue est un responsive complet pilote par plusieurs pages Figma par largeur, fusionne en une seule page finale par famille, tout en restant strictement dans l'idiome Hugo.

Cela implique :

- une page finale = une route Hugo normale
- `content/` pilote le routage et le front matter
- `data/` porte les donnees fusionnees
- `layouts/` et `partials/` portent le rendu
- `assets/css/` porte le responsive
- aucun runtime JS ne reconstruit le layout responsive cote client
- le build de verite reste `hugo`

## Cas Pilote De Reference

Pages Figma de reference pour le chantier :

- `https://www.figma.com/design/ujsdblUfnAeBvP7Aq279gv/OLD---maquette_embedded--GRAND?node-id=4038-100&t=QEtDTYAeiIvCByeP-4`
- `https://www.figma.com/design/ujsdblUfnAeBvP7Aq279gv/OLD---maquette_embedded--GRAND?node-id=4038-73&t=QEtDTYAeiIvCByeP-4`
- `https://www.figma.com/design/ujsdblUfnAeBvP7Aq279gv/OLD---maquette_embedded--GRAND?node-id=2031-180&t=QEtDTYAeiIvCByeP-4`

## Etat Initial Constate Avant Cette Passe

### Deja Present

- detection des familles responsive via `page-<slug>-<width>`
- merge de variantes dans `src/figma2hugo/generators/_responsive.py`
- emission de `@media (max-width: ...)` dans `src/figma2hugo/generators/css/generator.py`
- validation multi-viewports dans `src/figma2hugo/validator/validator.py`
- composants deja un peu `responsive-friendly` :
  - accordion
  - link-grid
  - link-card
  - carousel
  - form fields
  - section-block

### Faiblesses Observees

- un cas degenere pouvait encore remonter un `breakpoints: [1920]` avec `base_width: 1920`
- le validateur declarait encore le merge multi-variantes comme "non garanti"
- le report ne remontait pas clairement les familles responsive detectees
- les warnings de merge responsive n'etaient pas exposes dans une zone dediee du report
- sur un site Hugo avec une seule page fusionnee, le validateur pouvait viser la home au lieu de la route de page issue du manifest

## Ce Qui Est Implante Maintenant

### 1. Contrat De Merge Responsive Durci

Statut : `[x] fait`

Fichier principal :
- `src/figma2hugo/generators/_responsive.py`

Comportements maintenant imposes :

- au moins 2 variantes sont requises pour lancer un merge responsive
- chaque variante doit avoir un slug suffixe par largeur
- toutes les variantes passees au merge doivent appartenir a la meme famille
- les largeurs dupliquees sont refusees explicitement
- les breakpoints de sortie ne contiennent plus que des largeurs strictement inferieures a la largeur de base
- la sortie `responsive` expose une base claire :
  - `family`
  - `base_width`
  - `breakpoints`
  - `variants`

Warnings de structure ajoutes :

- si des siblings reutilisent le meme token logique sous un meme parent, un warning explicite est emis
- le warning explique que le matching va alors reposer sur l'ordre des siblings

### 2. Matching Et Warnings De Differences

Statut : `[x] deja present puis consolide`

Fichier principal :
- `src/figma2hugo/generators/_responsive.py`

Le merge emet maintenant ou continue d'emettre des warnings quand une variante change :

- le texte d'un item partage
- la source d'un asset partage
- le type d'un controle de formulaire partage

Doctrine retenue :

- si le contenu change vraiment, l'element doit etre duplique comme item specifique au breakpoint
- on ne confie pas ce choix au navigateur

### 3. Validation Hugo Plus Fidele A La Realite Du Site

Statut : `[x] fait`

Fichier principal :
- `src/figma2hugo/validator/validator.py`

Corrections apportees :

- quand un `site.json` Hugo est present, le validateur traite le rendu comme un vrai site Hugo meme s'il n'y a qu'une seule page fusionnee
- les checks de textes/assets s'appuient alors sur les routes issues du manifest
- les cibles HTML de validation responsive/interactions s'appuient aussi sur le manifest

Impact concret :

- une famille responsive fusionnee vers une seule page n'est plus confondue avec la home du site

### 4. Report Responsive Enrichi

Statut : `[x] fait`

Fichier principal :
- `src/figma2hugo/validator/validator.py`

Nouveaux champs dans `report["responsive"]` :

- `families`
- `summary.familyCount`
- `summary.familiesWithWarnings`

Chaque famille remontee expose :

- `page`
- `family`
- `baseWidth`
- `breakpoints`
- `sourceWidths`
- `variantCount`
- `warnings`

Objectif :

- savoir tout de suite si la famille detectee est propre
- voir quels breakpoints ont ete retenus
- voir si le merge a emis des incoherences

### 5. Scope Produit / Support Matrix Alignes

Statut : `[x] fait`

Fichiers :
- `docs/support-matrix.md`
- `docs/cahier-des-charges-responsive.md`

Alignement effectue :

- le merge responsive multi-variantes n'est plus presente comme "non garanti" sans nuance
- la doc rappelle explicitement l'idiome Hugo
- la doc rappelle qu'il n'y a pas de merge layout cote navigateur

### 6. Nettoyage Et Perennite Des Sorties Hugo

Statut : `[x] deja en place dans les passes recentes`

Fichiers :
- `src/figma2hugo/generators/hugo/generator.py`
- `src/figma2hugo/validator/validator.py`

Etat actuel :

- suppression des anciens bundles multi-pages orphelins
- build Hugo avec `--cleanDestinationDir`

### 7. Split Automatique Des Boards Responsives Uniques

Statut : `[x] fait`

Fichiers :
- `src/figma2hugo/figma_reader/service.py`
- `src/figma2hugo/workflow.py`

Ce qui est maintenant supporte :

- un parent Figma unique peut contenir plusieurs frames top-level nommees `page-<slug>-<width>`
- une seule URL Figma peut donc produire plusieurs documents internes
- le workflow Hugo reutilise ensuite le merge responsive normal sans moteur parallele

Comportement :

- les frames top-level visibles de type conteneur sont inspectees
- si au moins deux frames correspondent a la meme famille `page-*`
- elles sont extraites comme variantes internes triees par largeur decroissante
- chaque variante garde son propre `page.json` dans le workspace de debug
- la generation finale produit ensuite une seule page Hugo fusionnee

Limite volontaire :

- le split automatique ne s'active pas si les frames `page-*` top-level appartiennent a plusieurs familles differentes
- dans ce cas, il faut encore fournir les variantes de maniere explicite

## Tests De Regression En Place

### Generateur

Fichier :
- `tests/test_generators.py`

Cas couverts :

- merge responsive nominal desktop + mobile
- emission du breakpoint attendu
- item specifique a un breakpoint cache par defaut puis visible au bon breakpoint
- warning si un texte partage change entre largeurs
- erreur si deux variantes reutilisent la meme largeur
- erreur si des familles differentes sont forcees dans le meme merge
- warning si le matching doit s'appuyer sur des siblings dupliques

### Validateur

Fichier :
- `tests/test_validator.py`

Cas couverts :

- support scope coherent avec la strategie actuelle
- responsive report multi-viewports
- detection d'overflow horizontal
- reporting de famille responsive pour une page Hugo fusionnee
- compatibilite du flux avec une page Hugo unique issue d'un `site.json`

### GUI

Fichier :
- `tests/test_gui.py`

Cas couverts :

- detection de configuration Figma disponible ou manquante
- nettoyage des URLs saisies
- feedback de selection pour une URL unique ou plusieurs URLs
- resume lisible apres succes de generation

## Etat D'Avancement Par Chantiers

### A. Contrat D'Entree Responsive

- `[x]` convention `page-<slug>-<width>`
- `[x]` familles melangees refusees au merge
- `[x]` largeurs dupliquees refusees
- `[ ]` detection produit d'une famille "incomplete" selon une grille officielle de largeurs

Remarque :
- le moteur sait verifier la coherence de ce qu'on lui donne
- il ne force pas encore une liste de largeurs obligatoire commune a tous les projets

### B. Merge Des Variantes

- `[x]` plus grande largeur conservee comme base
- `[x]` variantes secondaires injectees seulement si plus petites que la base
- `[x]` warnings de differences de texte
- `[x]` warnings de differences d'assets
- `[x]` warnings de differences de type de controle
- `[x]` warnings de collisions de siblings
- `[ ]` warnings plus fins sur derives de parent logique entre variantes
- `[ ]` warnings plus fins sur ordre instable de wrappers tres generiques

### C. Sortie Hugo

- `[x]` une famille fusionnee produit une seule page finale
- `[x]` une famille fusionnee produit un seul JSON final
- `[x]` une famille fusionnee produit une seule feuille CSS finale
- `[x]` sortie toujours dans `content/`, `data/`, `layouts/`, `assets/`
- `[x]` aucun runtime JS de merge
- `[x]` une seule URL peut maintenant alimenter plusieurs variantes internes si le parent contient des frames top-level `page-*`

### D. CSS Responsive

- `[x]` `@media (max-width: ...)` emis a partir des variantes secondaires
- `[x]` relecture des geometries de sections et nodes par breakpoint
- `[x]` visibilite des items specifiques a un breakpoint
- `[x]` overrides des vrais controles de formulaire
- `[ ]` couverture exhaustive de tous les shells de page complexes
- `[ ]` couverture exhaustive des composants encore absolus ou semi-absolus

### E. Validation Et Reporting

- `[x]` sondes multi-viewports
- `[x]` sondes d'interaction
- `[x]` resume par overflow / broken images
- `[x]` resume par famille responsive
- `[ ]` integration automatique d'une validation Playwright reelle dans tous les environnements

### F. Documentation

- `[x]` support matrix alignee
- `[x]` cahier des charges aligne
- `[x]` fichier memoire / progression detaille
- `[ ]` guide utilisateur final pas-a-pas de creation de familles responsive dans Figma

### G. UI Et Experience Operateur

- `[x]` support du board unique responsive dans le workflow
- `[x]` hint UI expliquant les modes d'entree possibles
- `[x]` activation dynamique du mode Statique selon le nombre d'URLs
- `[x]` suppression de lignes d'URL en plus de l'ajout
- `[x]` affichage ou masquage du token Figma
- `[x]` retour de succes plus lisible qu'un JSON brut
- `[x]` barre de progression d'activite pendant la generation
- `[x]` scroll vertical de l'interface
- `[x]` log de lancement plus informationnel
- `[x]` suivi temps reel des etapes pendant la generation
- `[ ]` persistance des dernieres URLs et du dernier dossier de sortie
- `[ ]` ouverture directe du rapport ou du dossier de debug en cas d'erreur
- `[x]` extraction d'un presenter GUI pour les messages, logs et diagnostics
- `[ ]` structuration du code GUI en sous-composants Tkinter plus fins

### H. Factorisation, Nettoyage Et Optimisation Globaux

- Priorite actuelle :
  - le responsive pilote etant valide, le chantier principal est maintenant la factorisation, le nettoyage et l'optimisation du projet complet
- Backlog non prioritaire a ce stade :
  - garde-fou plus strict sur les siblings critiques portant exactement le meme nom, en particulier des cards soeurs reutilisant un nom identique entre variantes

- `[x]` isoler les helpers communs de reporting et de progression
- `[x]` rationaliser les helpers du workflow entre extraction simple et multi-documents
- `[x]` nettoyer les generateurs CSS, statique et Hugo sur les zones chaudes
- `[x]` poser un premier socle de helpers communs dans `_shared.py`
- `[x]` clarifier le contrat de document intermediaire entre extraction et workflow
- `[x]` extraire le regroupement responsive post-modele hors du generateur Hugo
- `[ ]` separer clairement les responsabilites extraction / transformation / rendu / validation
- `[ ]` reduire les branches legacy devenues obsoletes depuis le mode lightweight unique
- `[ ]` harmoniser les structures de rapport entre GUI, CLI et validator
- `[ ]` nettoyer les docs de crash-tests et variantes encore sur les anciens widths `768/390`
- `[ ]` revoir les duplications de logique dans `gui.py`, `workflow.py`, `validator.py`
- `[ ]` etablir une passe d'optimisation par priorite :
  - UX
  - lisibilite code
  - robustesse
  - performances I/O et reseau

## Prochaines Etapes Recommandees

Etat au 2026-05-05 :
- la validation fonctionnelle responsive du cas pilote `page-mentions-legales` est fermee sur les sondes automatiques
- la generation reelle depuis Figma produit une famille fusionnee `1920 / 834 / 402`
- le report Playwright passe sur les viewports `1920`, `1440`, `1280`, `1024`, `834`, `402`
- le grand chantier de factorisation, nettoyage et optimisation transverse est en cours

Ordre recommande pour la suite :

1. poursuivre la grande passe projet :
   - duplication de logique entre `gui.py`, `workflow.py`, `validator.py` et les generateurs
   - branches legacy devenues inutiles depuis le mode lightweight unique
   - structures de rapport incoherentes entre GUI, CLI et validator
   - sorties locales et docs techniques de repro encore trop bruyantes
2. corriger en priorite cote rendu :
   - shells de page encore trop absolus
   - sections a gros risques d'overflow horizontal
   - composants visuels dont la geometrie varie fortement entre largeurs
3. ajouter ensuite seulement les garde-fous supplementaires de naming responsive :
   - warnings plus fins sur les derives de parent logique
   - garde-fou explicite sur des cards soeurs qui reutilisent exactement le meme nom
4. documenter enfin le workflow Figma de production responsive pour l'equipe

## Fichiers Cles Du Chantier

### Code

- `src/figma2hugo/generators/_responsive.py`
- `src/figma2hugo/generators/css/generator.py`
- `src/figma2hugo/generators/hugo/generator.py`
- `src/figma2hugo/validator/validator.py`

### Tests

- `tests/test_generators.py`
- `tests/test_validator.py`

### Docs

- `docs/support-matrix.md`
- `docs/cahier-des-charges-responsive.md`
- `docs/responsive-memory-and-progress.md`

## Journal De Progression

### 2026-05-04 - Passe 1 : fiabilisation du socle

- merge responsive durci
- doublons de largeur refuses
- familles melangees refusees
- breakpoints de sortie nettoyes
- warnings de collisions structurelles ajoutes
- validateur Hugo recale sur le manifest meme avec une seule page fusionnee
- report responsive enrichi avec les familles
- support scope aligne avec l'etat reel du moteur
- tests de regression ajoutes

### 2026-05-04 - Passe 2 : support du parent unique responsive

- extraction multi-documents depuis un board Figma unique
- split automatique des frames top-level `page-<slug>-<width>`
- compatibilite workflow pour une seule URL produisant plusieurs variantes
- garde-fou conserve : multi-documents reserve au mode Hugo
- tests ajoutes pour l'extraction et l'orchestration

### 2026-05-04 - Passe 3 : premier lot d'ameliorations UI

- hint dynamique sur les modes d'entree et le support des boards responsives
- activation ou desactivation du mode Statique en direct
- ajout de la suppression de lignes d'URL
- ajout d'un toggle pour afficher le token Figma
- ajout d'une barre de progression d'activite
- sortie de succes rendue plus lisible pour l'operateur
- premiers points de factorisation poses dans `gui.py`

### 2026-05-04 - Passe 4 : scroll vertical et journal enrichi

- ajout d'un conteneur principal scrollable verticalement
- ajout d'un journal de lancement avec contexte :
  - mode
  - nombre d'URLs
  - dossier cible
  - source d'acces Figma detectee
- conservation d'un log final lisible apres succes ou echec

### 2026-05-04 - Passe 5 : suivi live pendant la generation

- ajout d'un callback de progression dans le workflow
- emission des etapes en direct :
  - initialisation
  - extraction
  - validation intermediaire
  - generation du site
  - validation du site
  - ecriture du rapport
- affichage live de ces etapes dans la GUI avec statuts courts et journal append-only

### 2026-05-04 - Passe 6 : molette et log live plus detaille

- ajout du scroll molette global sur le shell principal
- preservation du scroll natif dans la zone de log elle-meme
- enrichissement des evenements live avec :
  - source Figma courante
  - nom du document ou de la variante
  - largeur de variante quand elle est connue
  - resume des documents detectes
  - dossier cible, rapport final et nombre de warnings

### 2026-05-04 - Passe 7 : correctif responsive sur identites CSS et DOM

- correction d'un bug de merge responsive sur les items presents uniquement en tablette ou mobile
- les nodes, textes, assets et controles de formulaire ajoutes par une variante recoivent maintenant une identite de rendu unique
- suppression des collisions de classes entre desktop et variantes specifiques
- suppression des collisions d'identifiants DOM sur les sous-arbres ajoutes
- ajout d'un test de regression pour un hero desktop avec wrapper tablette specifique portant le meme naming de texte
- regeneration de verification relancee sur le cas `page-mentions-legales`

### 2026-05-04 - Passe 8 : fallback de shell entre variantes

- ajout d'un wrapper Hugo `page-shell` autour de la page finale
- ajout d'un runtime leger `page-shell.js` pour ajuster l'echelle d'un shell fixe a la largeur disponible
- couverture continue des largeurs intermediaires entre deux variantes Figma, sans tranche horizontale visible
- conservation du mode responsive multi-variantes existant : le fallback n'invente pas une nouvelle maquette, il ajuste seulement l'affichage du shell fixe
- verification relancee sur `page-mentions-legales`

### 2026-05-04 - Passe 9 : assainissement des absences responsive et mesure de shell

- correction des absences responsive au niveau CSS :
  - les containers absents dans une variante etroite sont maintenant masques
  - les assets decoratifs absents sont maintenant masques
  - les backgrounds absents utiles peuvent rester visibles comme fallback
- ajout d'un fallback local pour les backgrounds herites absents :
  - si le parent responsive est present mais pas son background dedie, le background herite remplit maintenant le parent au lieu de garder sa geometrie desktop
- suppression du blocage qui empechait certaines sections compactes de sortir leur vraie geometrie responsive
- correction du runtime `page-shell.js` :
  - mesure de la largeur disponible depuis le shell externe
  - mesure de la largeur et hauteur utiles depuis les sections visibles au lieu de `scrollWidth`
- verification reelle relancee sur `page-mentions-legales` :
  - `900px` : desktop fit conserve
  - `430px` : variante `834` lisible, sans bloc contact desktop herite
  - `402px` : variante mobile compacte rendue correctement

### 2026-05-04 - Passe 10 : variants d'images par breakpoint et clarification des priorites

- le merge responsive sait maintenant garder des assets distincts quand une meme image logique change reellement entre variantes
- la visibilite CSS responsive preserve le contenu absent tant qu'il n'existe pas de remplaçant explicite au meme niveau logique
- diagnostic fonctionnel retenu sur le texte :
  - des cards soeurs portant exactement le meme nom rendent le matching responsive ambigu
  - ce point est documente comme garde-fou futur, mais n'est pas la priorite immediate
- priorite de chantier recadree :
  - d'abord validation complete du responsive pilote
  - ensuite grande passe transversale de factorisation, nettoyage et optimisation du projet complet

### 2026-05-04 - Passe 11 : correctif d'extraction sur les paragraphes mobiles

- identification de la vraie cause du bug mobile sur `page-mentions-legales` :
  - le rebuild Hugo et le CSS etaient bons
  - la variante `402` extraite contenait deja un premier paragraphe geant qui absorbait le texte des cards suivantes
- cause technique :
  - la fusion des "paragraph line clusters" dans l'extracteur regroupait les lignes par `sectionId` + style seulement
  - plusieurs paragraphes soeurs portant le meme naming et la meme typo pouvaient donc etre fusionnes a travers plusieurs cards
- correctif applique :
  - chaque texte extrait conserve maintenant aussi son `parentId` et son `parentName`
  - la fusion de lignes de paragraphe est maintenant scopee par parent direct
- effet attendu :
  - les paragraphes multi-lignes d'une meme card continuent a etre reconstruits
  - les paragraphes de cards soeurs ne peuvent plus etre absorbes dans le premier bloc
- regression ajoutee :
  - test extracteur pour deux cards soeurs avec des lignes de paragraphe homonymes

### 2026-05-05 - Passe 12 : validation reelle du pilote responsive

- regeneration reelle du cas pilote depuis les trois URLs Figma de reference
- sortie de verification :
  - `.figma2hugo-scratch/pilot-responsive-20260505`
  - `.figma2hugo-scratch/pilot-responsive-20260505/report.json`
- resultat generation / build :
  - `buildOk: true`
  - `missingAssets: []`
  - `missingTexts: []`
  - warnings restants limites au contexte normal d'execution :
    - MCP optionnel non installe
    - `fidelityMode=balanced`
    - `contentMode=data-file`
- resultat responsive :
  - famille detectee : `page-mentions-legales`
  - `baseWidth: 1920`
  - `breakpoints: [834, 402]`
  - `sourceWidths: [1920, 834, 402]`
  - `familiesWithWarnings: 0`
  - sondes Playwright propres sur `1920`, `1440`, `1280`, `1024`, `834`, `402`
  - `horizontalOverflowCount: 0`
  - `brokenImageCount: 0`
- correctifs appliques pour fermer les faux positifs / regressions :
  - le validateur ne compte plus le `scrollWidth` interne non scale d'un shell fixe transforme comme overflow navigateur
  - les images `loading=lazy` sont forcees en eager pendant la sonde et les images non visibles ne sont plus comptees comme cassees
  - les placeholders et options de formulaires transformes en vrais controles HTML ne sont plus reportes comme textes manquants
  - le check d'interaction formulaire ignore proprement un formulaire present dans le DOM mais masque sur mobile
  - le CSS formulaire utilise `:where(...)` pour ne plus battre les dimensions absolues generees par page
- regressions executees :
  - `201 passed`
- note outillage :
  - `playwright` et son Chromium ont ete installes localement pour la validation reelle
  - l'installation editable complete `[dev]` reste bloquee sur `lxml` avec Python 3.14 faute de wheel compatible / build tools C++
  - `ruff` global remonte encore du bruit historique sur tout le repo ; ce n'est pas traite dans cette passe

### 2026-05-05 - Passe 13 : premier lot de factorisation transverse

- extraction d'un helper partage de reporting :
  - `src/figma2hugo/reporting/utils.py`
  - fonction `dedupe_warnings`
- remplacement des duplications de dedupe dans :
  - `src/figma2hugo/workflow.py`
  - `src/figma2hugo/validator/validator.py`
  - `src/figma2hugo/figma_reader/service.py`
  - `src/figma2hugo/generators/_responsive.py`
- extraction du formatage de progression GUI dans :
  - `src/figma2hugo/progress.py`
- la GUI conserve ses noms prives existants par import alias, pour ne pas casser les tests ni l'API interne actuelle
- ajout d'un test dedie :
  - `tests/test_reporting.py`
- nettoyage non destructif du bruit de repo :
  - `.gitignore` ignore maintenant les sorties racine `tmp*`, `tmp*.txt`, `tmp*.png`, `tmp*.webp` et `repro*`
  - aucun dossier de repro existant n'a ete supprime
- regressions executees :
  - ciblage workflow / GUI / validator / extraction / generateurs : `131 passed`
  - suite complete : `202 passed`
- controle statique :
  - `ruff` OK sur les nouveaux fichiers `progress.py`, `reporting/utils.py`, `tests/test_reporting.py`
  - `ruff` global reste volontairement hors scope car le repo contient encore du bruit historique

### 2026-05-05 - Passe 14 : decoupage de l'orchestration workflow

- extraction du bloc extraction / validation hors de `run_generation` :
  - `_extract_and_validate_documents`
  - `_extract_single_input_documents`
  - `_extract_multi_input_documents`
- conservation du contrat de progression existant :
  - les evenements single URL gardent les memes `stage` et metadonnees
  - les diagnostics d'erreur continuent a pointer le dernier stage actif
- clarification du choix de reference visuelle :
  - la validation compare a la reference Figma seulement pour une entree unique produisant un seul document
  - les splits responsive / multi-pages evitent donc une comparaison visuelle mono-capture trompeuse
- nettoyage opportuniste de `workflow.py` :
  - import `Callable` depuis `collections.abc`
  - lignes longues cassees
  - acces d'attribut simplifie pour la largeur de page
- regressions executees :
  - ciblage workflow / GUI / reporting : `22 passed`
- controle statique :
  - `ruff` OK sur `src/figma2hugo/workflow.py`

### 2026-05-05 - Passe 15 : decoupage du validateur

- simplification du deroule principal de `SiteValidator.validate` :
  - creation du rapport initial dans `_new_validation_report`
  - validation assets/textes/modeles dans `_populate_content_validation`
  - comparaison visuelle optionnelle dans `_populate_visual_validation`
  - deduplication finale dans `_finalize_report`
- le code de sondes Playwright responsive / interactions reste fonctionnellement identique
- nettoyage de lisibilite de `validator.py` :
  - lignes longues cassees
  - commandes Hugo et resolutions d'assets rendues plus lisibles
  - warnings de rapport deduplicables via le helper commun de reporting
- regressions executees :
  - ciblage validator : `14 passed`
  - ciblage workflow / GUI / reporting : `22 passed`
  - suite complete : `202 passed`
- controle statique :
  - `ruff` OK sur `src/figma2hugo/validator/validator.py`

### 2026-05-05 - Passe 16 : nettoyage des generateurs statique et Hugo

- nettoyage de `StaticGenerator` :
  - `generate` delegue maintenant la construction de contexte, le rendu et l'ecriture du bundle
  - le fallback HTML sans Jinja est plus lisible
  - correction d'un f-string de `<option selected>` compatible seulement avec Python recent
  - extraction de petits helpers internes pour les roles de noeuds et options de select
- nettoyage de `HugoGenerator` :
  - imports tries
  - signatures et retours longs reformates
  - ecritures de bundle / manifest rendues plus lisibles sans changer les chemins produits
- assainissement cible dans `_shared.py` :
  - import explicite de `Iterable`
  - suppression d'une redefinition de regex de ponctuation
  - regex de listes non ordonnees exprimee en escapes Unicode lisibles par Python
- regressions executees :
  - ciblage generateurs : `87 passed`
  - ciblage generateurs + extracteur : `124 passed`
  - ciblage generateurs / validator / workflow / GUI / reporting : `123 passed`
  - suite complete : `202 passed`
- controle statique :
  - `ruff` OK sur `static/generator.py`, `hugo/generator.py`, `workflow.py`, `validator.py`, `progress.py`, `reporting/utils.py`, `tests/test_reporting.py`
  - `ruff --select I,F821` OK sur `_shared.py`

### 2026-05-05 - Passe 17 : nettoyage du generateur CSS

- nettoyage de `CssGenerator` sans changement de comportement attendu :
  - imports tries et import inutilise supprime
  - constantes responsive multi-lignes
  - signatures longues reformatees
  - calculs de largeur / hauteur de section clarifies par variables intermediaires
  - blocs de geometrie et de responsive overrides rendus lisibles sans changer les selecteurs produits
- le generateur CSS est maintenant propre au lint complet cible
- controles conserves autour du responsive :
  - `tests/test_generators.py`
  - `tests/test_validator.py`
  - `tests/test_workflow.py`
  - `tests/test_gui.py`
  - `tests/test_content_extractor.py`
  - `tests/test_extraction_service.py`
- regressions executees :
  - ciblage generateurs / validator / workflow / GUI : `122 passed`
  - ciblage generateurs / extracteur / extraction / validator : `146 passed`
  - suite complete : `202 passed`
- controle statique :
  - `ruff` OK sur `src/figma2hugo/generators/css/generator.py`
  - `ruff` OK sur les generateurs statique et Hugo
  - `ruff --select I,F821` OK sur `_shared.py`

### 2026-05-05 - Passe 18 : assainissement des helpers partages de generation

- nettoyage en profondeur cible de `src/figma2hugo/generators/_shared.py` :
  - helpers de chemins d'assets :
    - `asset_destination_path`
    - `fallback_asset_filename`
    - `static_images_index`
  - helper de geometrie :
    - `bounds_area`
  - helpers de valeurs CSS :
    - `format_css_number`
    - `normalize_css_literal`
- normalisation du builder canonique rendue plus lisible :
  - calculs de page, layout, section, node, texte et asset sortis en variables explicites
  - petits helpers dedies pour tags de texte, controles de formulaire, enfants geometriques et offsets de bounds
  - deduplication des classes stabilisee par compteur interne
- tests directs ajoutes dans `tests/test_generators.py` pour :
  - destinations d'assets en mode statique et Hugo
  - normalisation des nombres / unites CSS
  - declarations CSS courantes issues de `style_map_to_css`
- regressions executees :
  - ciblage generateurs : `90 passed`
  - ciblage generateurs / extracteur / extraction / validator : `149 passed`
  - suite complete : `205 passed`
- controle statique :
  - `ruff --select E501` OK sur `_shared.py`
  - `ruff --select I,F` OK sur `_shared.py` et `tests/test_generators.py`

### 2026-05-05 - Passe 19 : contrat extraction vers modele intermediaire

- ajout d'une API de contrat dans `src/figma2hugo/model/intermediate.py` :
  - `validate_intermediate_payload`
  - `serialize_intermediate_payload`
  - `intermediate_document_name`
  - `intermediate_document_width`
  - `intermediate_document_names`
- le workflow reutilise maintenant ces helpers pour :
  - valider les payloads extraits
  - afficher les noms de documents dans la progression
  - recuperer la largeur de breakpoint sans dupliquer la lecture du payload
- le service Figma serialise maintenant les `page.json` via le meme contrat de modele
- decoupage de `FigmaExtractionService._extract_document_from_root` :
  - `_build_intermediate_payload`
  - `_page_meta`
  - `_page_payload`
  - `_section_payload`
  - `_section_text_ids`
  - `_section_asset_ids`
  - `_section_metadata`
- objectif atteint :
  - la frontiere `Figma raw / sections / ExtractionResult / IntermediateDocument` est plus explicite
  - la validation Pydantic reste la source de verite
  - la generation continue de recevoir le meme modele serialise
- tests ajoutes dans `tests/test_models.py` :
  - validation et serialisation via le contrat partage
  - resume nom / largeur depuis un dict ou un `IntermediateDocument`
  - erreur stable `ValueError` sur payload invalide
- regressions executees :
  - ciblage modele / workflow / extraction : `24 passed`
  - ciblage modele / workflow / extraction / content / generateurs : `151 passed`
  - suite complete : `207 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur les fichiers touches

### 2026-05-05 - Passe 20 : presenter GUI et nettoyage de presentation

- extraction d'un module de presentation GUI :
  - `src/figma2hugo/gui_presenter.py`
- logique pure sortie de `gui.py` :
  - detection d'acces Figma
  - nettoyage des URLs
  - disponibilite du mode statique
  - messages de selection
  - logs de lancement
  - resume de succes
  - classification des erreurs de generation
- `gui.py` conserve des wrappers prives compatibles avec les tests et l'UI existante :
  - les monkeypatchs sur `get_local_figma_token` restent effectifs
  - la mecanique Tkinter reste separee des decisions de presentation
- nettoyage opportuniste :
  - import `re` retire de `gui.py`
  - lignes longues GUI et tests GUI reformatees
  - `gui.py`, `gui_presenter.py` et `tests/test_gui.py` sont propres au lint cible
- regressions executees :
  - ciblage GUI : `14 passed`
  - ciblage GUI / workflow / modeles : `30 passed`
  - ciblage GUI / workflow / modeles / reporting / validator / generateurs : `135 passed`
  - suite complete : `207 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur `gui.py`, `gui_presenter.py`, `tests/test_gui.py`

### 2026-05-06 - Passe 21 : regroupement responsive post-modele

- extraction du regroupement des pages responsives vers `src/figma2hugo/generators/_responsive.py` :
  - nouvelle fonction `merge_responsive_page_groups`
  - regroupement par famille `page-<slug>-<width>`
  - preservation des pages non responsives dans leur ordre d'apparition
  - conservation d'une variante width-suffixee seule sans tentative de merge
- `HugoGenerator.generate_many` delegue maintenant cette transformation au module responsive :
  - le generateur Hugo reste responsable du scaffold, des assets, du CSS et des fichiers
  - le module responsive porte la logique de detection / fusion / regroupement des variantes
- tests directs ajoutes dans `tests/test_generators.py` :
  - merge d'une famille responsive intercalee entre deux pages normales
  - preservation d'une variante unique non fusionnable
- nettoyage cible de `src/figma2hugo/generators/_responsive.py` :
  - imports tries
  - formatage Ruff
  - lignes longues restantes repliees sur le module responsive
- regressions executees :
  - ciblage generateurs : `92 passed`
  - ciblage generateurs / workflow / modeles / extraction / validator : `130 passed`
  - suite complete : `209 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur `_responsive.py` et `hugo/generator.py`
  - `ruff --select I,F` OK sur `tests/test_generators.py`

### 2026-05-06 - Passe 22 : preparation post-canonique Hugo multi-pages

- nettoyage cible de `HugoGenerator.generate_many` :
  - la construction du bundle multi-page est sortie dans `_prepare_multi_page_bundles`
  - un petit objet interne `_MultiPageBundle` porte maintenant la page scopee, le slug, le poids et l'entree de manifeste
  - la fabrication d'une entree `site.json` est isolee dans `_site_page_entry`
  - le chemin CSS par page passe par `_page_stylesheet_path`, partage par le manifeste et l'ecriture du bundle
- objectif atteint :
  - la boucle principale de generation multi-page ne melange plus slugging, scoping, manifeste et ecriture disque
  - les sorties restent identiques : contenus Hugo, CSS par page, `data/pages/*.json`, `data/site.json`
  - le rendu HTML/CSS n'a pas ete modifie
- regression renforcee dans `tests/test_generators.py` :
  - verification du manifeste multi-page complet
  - verification du `page_data` retourne par `generate_many`
  - verification des front matters multi-pages (`page_key`, `stylesheet`, `weight`)
- regressions executees :
  - ciblage generateurs : `92 passed`
  - ciblage generateurs / workflow / modeles / extraction / validator : `130 passed`
  - suite complete : `209 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur `hugo/generator.py`
  - `ruff --select I,F` OK sur `tests/test_generators.py`

### 2026-05-06 - Passe 23 : preparation post-canonique statique

- nettoyage cible de `StaticGenerator.generate` :
  - extraction de `_prepare_static_page_bundle`
  - ajout d'un petit objet interne `_StaticPageBundle`
  - la generation statique separe maintenant clairement :
    - construction du modele canonique
    - preparation du contexte
    - rendu HTML / CSS
    - ecriture du bundle disque
- objectif atteint :
  - `generate` devient symetrique avec la passe Hugo precedente
  - le rendu HTML/CSS reste identique
  - le contrat `GenerationArtifacts.page_data` reste aligne sur `page.json`
- regression renforcee dans `tests/test_generators.py` :
  - verification de l'ecriture de `report.json`
  - verification que `result.page_data` correspond exactement au payload `page.json`
  - verification que `report.json` est inclus dans `written_files`
- regressions executees :
  - ciblage generateurs : `93 passed`
  - ciblage generateurs / workflow / modeles / extraction / validator : `131 passed`
  - suite complete : `210 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur `static/generator.py`
  - `ruff --select I,F` OK sur `tests/test_generators.py`

### 2026-05-06 - Passe 24 : support de generation partage

- factorisation transverse dans `src/figma2hugo/generators/_shared.py` :
  - `write_generation_report` centralise l'ecriture optionnelle de `report.json`
  - `page_contains_assets` centralise la detection d'assets sur un payload canonique
  - `ensure_asset_output_directory` centralise le dossier d'assets attendu selon le mode (`images` en statique, `static/images` en Hugo)
- branchements generateurs :
  - `StaticGenerator` n'ecrit plus directement le rapport et ne calcule plus lui-meme le dossier d'assets
  - `HugoGenerator.generate` et `HugoGenerator.generate_many` reutilisent les memes helpers
- objectif atteint :
  - les chemins produits restent identiques
  - la logique de support apres rendu devient commune aux sorties statique et Hugo
  - les generateurs gardent leur responsabilite de rendu/ecriture du bundle principal
- regression renforcee dans `tests/test_generators.py` :
  - test direct du rapport optionnel
  - test direct de la detection d'assets
  - test direct des dossiers d'assets en modes statique et Hugo
- regressions executees :
  - ciblage generateurs : `94 passed`
  - ciblage generateurs / workflow / modeles / extraction / validator : `132 passed`
  - suite complete : `211 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur `_shared.py`, `static/generator.py`, `hugo/generator.py`
  - `ruff --select I,F` OK sur `tests/test_generators.py`

### 2026-05-06 - Passe 25 : presenter GUI pour etats d'interface

- extraction de logique de presentation supplementaire vers `src/figma2hugo/gui_presenter.py` :
  - ajout de `GuiControlStates`
  - ajout de `control_states`
  - ajout de `generation_launch_summary`
- branchement dans `src/figma2hugo/gui.py` :
  - `_set_running_state` applique maintenant un view model calcule par le presenter
  - le bouton statique reutilise la meme regle pendant l'execution et pendant le feedback d'input
  - le resume de lancement n'est plus recompose directement dans la classe Tkinter
- objectif atteint :
  - `gui.py` reste responsable des widgets Tkinter
  - les decisions d'etat activable/desactivable deviennent testables sans UI
  - le comportement existant est conserve pour le mode statique mono-URL / multi-URL et l'etat running
- regressions ajoutees dans `tests/test_gui.py` :
  - etats de controles pour URL unique, multi-URLs et generation en cours
  - pluriel du resume de lancement
- regressions executees :
  - ciblage GUI : `16 passed`
  - ciblage GUI / workflow / modeles / reporting / validator : `47 passed`
  - suite complete : `213 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur `gui.py`, `gui_presenter.py`, `tests/test_gui.py`

### 2026-05-06 - Passe 26 : integration production-like sans reseau Figma

- ajout d'un scenario d'integration realiste dans `tests/test_workflow.py` :
  - service d'extraction factice `ProductionLikeBoardExtractionService`
  - board Figma simule avec :
    - une famille responsive `page-services-1920` / `page-services-402`
    - une page classique `contact-page`
  - passage par le vrai `run_generation`
  - generation Hugo reelle
  - build Hugo reel via `SiteValidator`
  - rapport final reel `report.json`
- les sondes Playwright restent desactivees dans ce test pour conserver une regression deterministe :
  - la validation du build Hugo, du manifest, du merge responsive, des textes et du rapport reste couverte
  - les vraies pages Figma pourront ensuite etre validees avec Playwright dans un chantier de validation dedie
- assertions couvertes :
  - `data/site.json` contient `page-services` puis `contact-page`
  - le payload `page-services` porte la famille responsive attendue
  - `public/page-services/index.html` et `public/contact-page/index.html` sont produits
  - `missingTexts` et `missingAssets` restent vides
  - le rapport contient les warnings de mode deduplicables (`fidelityMode`, `contentMode`)
  - le workspace temporaire est nettoye
  - les evenements de progression exposent les noms de documents extraits
- nettoyage cible :
  - `tests/test_workflow.py` est maintenant propre sur imports, references et lignes longues ciblees
- regressions executees :
  - ciblage workflow : `8 passed`
  - ciblage workflow / generateurs / validator / reporting / modeles : `126 passed`
  - suite complete : `214 passed`
- controle statique :
  - `ruff --select I,F,E501` OK sur `tests/test_workflow.py`

### 2026-05-06 - Passe 27 : harnais optionnel pour vraies URLs Figma

- ajout de `tests/test_real_figma_integration.py` :
  - parsing de `FIGMA2HUGO_REAL_FIGMA_URLS`
  - support des separateurs newline, `;` et `,`
  - detection d'acces Figma via token local, variables d'environnement ou bridge MCP
  - generation Hugo reelle via `run_generation`
  - validation du rapport final :
    - `buildOk`
    - `missingTexts`
    - `missingAssets`
    - nombre de pages generees
    - absence d'overflow horizontal si les sondes responsive Playwright s'executent
- comportement par defaut :
  - le test de parsing s'execute toujours
  - le test Figma reel est skippe tant que `FIGMA2HUGO_REAL_FIGMA_URLS` n'est pas defini
  - la suite locale reste donc stable sans reseau ni credentials
- commande de validation reelle a utiliser quand les URLs sont disponibles :
  - PowerShell :
    - `$env:FIGMA2HUGO_REAL_FIGMA_URLS = "https://www.figma.com/design/...;https://www.figma.com/design/..."`
    - `$env:FIGMA2HUGO_REAL_FIGMA_OUT = ".figma2hugo-scratch/real-figma/site"`
    - `python -m pytest -p no:cacheprovider tests/test_real_figma_integration.py`
- regressions executees :
  - ciblage harnais reel : `1 passed, 1 skipped`
  - ciblage harnais reel / workflow : `9 passed, 1 skipped`
  - ciblage harnais reel / workflow / CLI / GUI / reporting : `32 passed, 1 skipped`
  - suite complete : `215 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `tests/test_real_figma_integration.py`

### 2026-05-06 - Passe 28 : fichier d'URLs pour build-site

- amelioration CLI dans `src/figma2hugo/cli.py` :
  - ajout de l'option `build-site --page-file`
  - `--page` devient optionnel si un fichier d'URLs est fourni
  - parsing commun des URLs :
    - lignes vides ignorees
    - lignes de commentaire `# ...` ignorees
    - separateurs newline, `;` et `,` acceptes
  - message d'erreur mis a jour : `--page` ou `--page-file`
- objectif atteint :
  - les vraies pages Figma peuvent etre conservees dans un fichier local non commite
  - les validations multi-pages / multi-familles deviennent plus simples a relancer
  - le workflow `run_generation` ne change pas
- regression ajoutee dans `tests/test_cli.py` :
  - `build-site` genere un site Hugo multi-pages depuis `--page-file`
  - verification des CSS par page et de `data/site.json`
- regressions executees :
  - ciblage CLI : `7 passed`
  - ciblage CLI / workflow / harnais reel : `16 passed, 1 skipped`
  - suite complete : `216 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `cli.py` et `tests/test_cli.py`

### 2026-05-06 - Passe 29 : garde-fou strict responsive opt-in

- ajout d'un mode strict dans `src/figma2hugo/generators/_responsive.py` :
  - `merge_responsive_family(..., strict_matching=True)`
  - `merge_responsive_page_groups(..., strict_matching=True)`
  - les siblings qui reutilisent le meme token sous un meme parent passent de warning a `ValueError`
- branchement Hugo :
  - `HugoGenerator` lit `FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING=1`
  - le mode par defaut reste tolerant pour ne pas casser les exports existants
  - le mode strict est pret pour valider les vraies pages Figma de production
- regression ajoutee dans `tests/test_generators.py` :
  - rejet strict des duplicate sibling tokens
  - le warning historique reste conserve en mode tolerant
- commande utile pour validation stricte :
  - `$env:FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING = "1"`
  - `python -m pytest -p no:cacheprovider tests/test_real_figma_integration.py`
- regressions executees :
  - ciblage generateurs : `95 passed`
  - ciblage generateurs / CLI / workflow / harnais reel / validator : `125 passed, 1 skipped`
  - suite complete : `217 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `_responsive.py` et `hugo/generator.py`
  - `ruff --select I,F` OK sur `tests/test_generators.py`

### 2026-05-06 - Passe 30 : validation reelle Figma sur 5 pages et nettoyage des faux ecarts

- URLs utilisateur placees dans `.figma2hugo-scratch/real-figma/pages.txt` :
  - `page-mentions-legales`
  - `page-a-propos`
  - `page-etude-de-cas`
  - `page-prestation-3`
  - `page-prestation-2`
- premiere validation reelle tolerante :
  - generation Hugo OK
  - 5 familles responsive reconnues
  - 30 viewports responsive controles
  - 0 overflow horizontal
  - 0 asset manquant
  - 28 faux `missingTexts`
  - 3 warnings d'interaction mobile
- corrections validateur dans `src/figma2hugo/validator/validator.py` :
  - les textes nommes `href-*` sont verifies dans le markup HTML, pas dans le texte visible
  - les balises inline (`span`, `strong`, `em`, etc.) ne creent plus d'espaces artificiels dans la normalisation du texte visible
  - cas reel couvert : un titre coupe par plusieurs `span` dans Figma est retrouve correctement dans le HTML
- correction CLI dans `src/figma2hugo/cli.py` :
  - `build-site --page-file` lit maintenant les fichiers `utf-8-sig`
  - un BOM UTF-8 en debut de fichier est ignore
  - objectif : rendre le workflow Windows/PowerShell robuste pour les fichiers d'URLs locaux
- corrections d'interaction mobile dans les CSS composants :
  - `templates/hugo/assets/css/components/carousel.css`
    - les blocs contenant un carousel passent au-dessus des textes voisins qui peuvent recouvrir les thumbnails
  - `templates/hugo/assets/css/components/accordion.css`
    - les triggers accordion en layout flow recuperent leur hauteur via `aspect-ratio`
    - fallback `min-height: 1px` pour eviter les boutons a hauteur nulle
- validation reelle finale :
  - commande :
    - `python -m figma2hugo.cli build-site --page-file .figma2hugo-scratch/real-figma/pages.txt .figma2hugo-scratch/real-figma/site`
  - `buildOk=True`
  - `missingTexts=0`
  - `missingAssets=0`
  - `warnings=30`
  - `responsive.familyCount=5`
  - `responsive.totalViewports=30`
  - `responsive.horizontalOverflowCount=0`
  - `responsive.brokenImageCount=0`
  - `interactions.totalChecks=40`
  - `interactions.passedChecks=21`
  - `interactions.failedChecks=0`
  - `interactions.skippedChecks=19`
  - `interactions.warnings=0`
- validation stricte observee pendant la passe :
  - `FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING=1` bloque encore `page-etude-de-cas`
  - cause : duplicate sibling token `text:heading:titre-h2-hero`
  - comportement attendu : le mode tolerant genere, le mode strict force le renommage/clarification de la maquette
- regressions ajoutees ou renforcees :
  - `tests/test_validator.py`
    - validation d'un titre coupe par des spans inline
    - validation d'une URL `href-*` dans les attributs HTML
  - `tests/test_cli.py`
    - `--page-file` avec fichier `utf-8-sig`
  - `tests/test_generators.py`
    - presence des garde-fous CSS carousel/accordion
- regressions executees :
  - ciblage validator : `15 passed`
  - ciblage CSS/CLI/validator : `8 passed`
  - ciblage CLI / generateurs / validator / workflow / harnais reel : `126 passed, 1 skipped`
  - suite complete : `218 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `src/figma2hugo/cli.py`, `src/figma2hugo/validator/validator.py`, `tests/test_cli.py`
  - `ruff --select I,F` OK sur `tests/test_generators.py` et `tests/test_validator.py`
  - note : `tests/test_generators.py` conserve des lignes longues historiques hors de cette passe

### 2026-05-06 - Passe 31 : synthese actionnable des issues responsive

- objectif :
  - rendre le rapport tolerant utile pour preparer le passage strict
  - transformer les warnings textuels responsive en donnees exploitables par page/famille
- ajout dans `src/figma2hugo/validator/validator.py` :
  - classification des warnings responsive en `responsive.families[].issues`
  - types actuellement reconnus :
    - `duplicate-sibling-token`
    - `text-content-change`
    - `board-split`
    - `responsive-warning` en fallback
  - severites :
    - `strict-blocker` pour les tokens siblings dupliques qui bloquent le mode strict
    - `review` pour les changements de texte entre breakpoints
    - `info` pour les board splits
  - chaque issue garde son `message` d'origine
  - les duplicats exposent aussi `width`, `token` et `parent`
  - les changements de texte exposent `width` et `path`
  - les board splits exposent `variant`
  - chaque famille expose maintenant `strictReady`
- nouveaux compteurs dans `responsive.summary` :
  - `issueCount`
  - `strictBlockingIssueCount`
  - `strictBlockingFamilyCount`
  - `strictReadyFamilyCount`
  - `duplicateSiblingTokenCount`
  - `textContentChangeCount`
  - `boardSplitCount`
- validation reelle sur le site Figma deja genere :
  - `buildOk=True`
  - `missingTexts=0`
  - `missingAssets=0`
  - `horizontalOverflowCount=0`
  - `brokenImageCount=0`
  - `interactionWarnings=0`
  - `responsive.issueCount=34`
  - `responsive.strictBlockingIssueCount=8`
  - `responsive.strictBlockingFamilyCount=3`
  - `responsive.strictReadyFamilyCount=2`
  - `responsive.duplicateSiblingTokenCount=8`
  - `responsive.textContentChangeCount=11`
  - `responsive.boardSplitCount=15`
- familles a corriger pour strict :
  - `page-etude-de-cas` :
    - 6 strict blockers
    - premier token : `text:heading:titre-h2-hero`
    - 2 changements de texte a relire
  - `page-prestation-3` :
    - 1 strict blocker
    - token : `node:section:section-embedded-infos-decouvre`
    - 5 changements de texte a relire
  - `page-prestation-2` :
    - 1 strict blocker
    - token : `node:section:section-embedded-infos-decouvre`
    - 4 changements de texte a relire
- regression ajoutee dans `tests/test_validator.py` :
  - classification d'un duplicate sibling token
  - classification d'un text content change
  - classification d'un board split
  - verification des compteurs de synthese
- regressions executees :
  - ciblage validator : `16 passed`
  - ciblage validator / harnais reel / workflow / generateurs : `120 passed, 1 skipped`
  - suite complete : `219 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `src/figma2hugo/validator/validator.py`
  - `ruff --select I,F` OK sur `tests/test_validator.py`

### 2026-05-06 - Passe 32 : audit responsive Markdown pour correction Figma

- objectif :
  - passer du rapport machine `report.json` a un document directement utilisable pour corriger les layers Figma
  - conserver le JSON comme source de verite pour l'automatisation
- ajout dans `src/figma2hugo/reporting/writer.py` :
  - `responsive_audit_markdown(report)`
  - `ReportWriter.write_responsive_audit(target_dir, report)`
  - ecriture de `responsive-audit.md` uniquement quand des familles responsive existent
- branchement workflow dans `src/figma2hugo/workflow.py` :
  - generation et validation ecrivent toujours `report.json`
  - si le writer le supporte, `responsive-audit.md` est ecrit en plus
  - les faux writers de tests restent compatibles grace a l'appel optionnel
- contenu de `responsive-audit.md` :
  - synthese :
    - familles responsive
    - familles strict-ready
    - familles bloquees en strict
    - issues strict bloquantes
    - changements de texte a relire
    - board splits
    - overflow horizontal
  - priorite 1 :
    - blocages stricts regroupes par famille, token et parent
    - les breakpoints concernes sont groupes sur une seule ligne
  - priorite 2 :
    - textes a arbitrer par breakpoint
  - familles deja strict-ready
  - rappel de verification apres corrections Figma
- validation reelle :
  - `responsive-audit.md` genere dans `.figma2hugo-scratch/real-figma/site/`
  - exemple reel :
    - `page-etude-de-cas` regroupe `text:heading:titre-h2-hero` sur 1920px/834px
    - `node:card:card-v-infos` regroupe 1920px/834px/402px
    - `page-prestation-3` et `page-prestation-2` ciblent `node:section:section-embedded-infos-decouvre` a 402px
- regressions ajoutees :
  - `tests/test_reporting.py`
    - generation Markdown avec strict blockers, texte a relire et famille strict-ready
    - ecriture de `responsive-audit.md` par `ReportWriter`
  - `tests/test_workflow.py`
    - le scenario Hugo responsive de production verifie la presence de l'audit
- regressions executees :
  - ciblage reporting/workflow : `3 passed`
  - ciblage reporting / workflow / validator / CLI : `34 passed`
  - suite complete : `221 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `src/figma2hugo/reporting/writer.py`, `src/figma2hugo/reporting/__init__.py`, `src/figma2hugo/workflow.py`, `tests/test_reporting.py`, `tests/test_cli.py`
  - `ruff --select I,F` OK sur `tests/test_workflow.py` et `tests/test_validator.py`

### 2026-05-06 - Passe 33 : lecture CLI de l'audit responsive

- objectif :
  - rendre `responsive-audit.md` accessible sans ouvrir manuellement le fichier
  - conserver `figma2hugo report` en JSON par defaut
- ajout CLI dans `src/figma2hugo/cli.py` :
  - `figma2hugo report <site> --responsive-audit`
  - affiche directement le contenu de `responsive-audit.md`
  - erreur claire si l'audit n'a pas encore ete genere
- validation reelle :
  - commande verifiee sur `.figma2hugo-scratch/real-figma/site`
  - sortie commence par la synthese :
    - `Familles responsive: 5`
    - `Familles strict-ready: 2`
    - `Familles bloquees en strict: 3`
    - `Issues strict bloquantes: 8`
- regressions ajoutees dans `tests/test_cli.py` :
  - affichage Markdown de l'audit
  - erreur si `responsive-audit.md` est absent
- regressions executees :
  - ciblage CLI/reporting : `6 passed`
  - suite complete : `223 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `src/figma2hugo/cli.py`, `tests/test_cli.py`, `src/figma2hugo/reporting/writer.py`, `tests/test_reporting.py`

### 2026-05-06 - Passe 34 : option CLI stricte responsive

- objectif :
  - rendre le mode strict responsive activable par commande, sans devoir connaitre le flag d'environnement interne
  - conserver la compatibilite avec `FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING=1`
- ajout CLI dans `src/figma2hugo/cli.py` :
  - `figma2hugo generate ... --strict-responsive-matching`
  - `figma2hugo build ... --strict-responsive-matching`
  - `figma2hugo build-site ... --strict-responsive-matching`
  - aide : le mode echoue quand le matching des siblings responsive est ambigu
- branchement workflow dans `src/figma2hugo/workflow.py` :
  - `GenerationOptions.strict_responsive_matching`
  - injection temporaire de `FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING=1` uniquement pendant l'appel generateur
  - restauration de l'environnement apres generation, y compris si une valeur existait avant le run
  - resultat CLI enrichi avec `strictResponsiveMatching`
- mise a jour audit dans `src/figma2hugo/reporting/writer.py` :
  - la section de verification recommande maintenant `--strict-responsive-matching`
  - le flag d'environnement reste documente comme compatibilite
- nettoyage transverse complementaire :
  - imports reordonnes par Ruff sur les modules detectes par le controle global
  - suppression d'une variable locale inutilisee dans `src/figma2hugo/layout_analyzer/analyzer.py`
- validation reelle :
  - aide `build-site --help` verifiee : l'option est exposee
  - `responsive-audit.md` regenere sur `.figma2hugo-scratch/real-figma/site`
  - run strict reel lance sur les 5 URLs via `--page-file`
  - echec attendu pendant `generating the output site` sur `page-etude-de-cas`
  - premier blocker strict confirme :
    - token : `text:heading:titre-h2-hero`
    - breakpoint : `1920px`
    - debug : `.figma2hugo-scratch/real-figma/site-strict-cli/.figma2hugo-debug/...`
- regressions ajoutees :
  - `tests/test_workflow.py`
    - le workflow active le flag strict pendant la generation puis restaure l'environnement
  - `tests/test_cli.py`
    - `build-site` transmet `strict_responsive_matching`
    - `generate` et `build` transmettent aussi le flag
- regressions executees :
  - ciblage strict CLI : `2 passed`
  - ciblage reporting/CLI/workflow/audit : `6 passed`
  - ciblage CLI/workflow/reporting/validator/integration reelle : `40 passed, 1 skipped`
  - ciblage nettoyage Ruff : `56 passed`
  - suite complete : `226 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F,E501` OK sur `src/figma2hugo/cli.py`, `src/figma2hugo/workflow.py`, `src/figma2hugo/reporting/writer.py`, `tests/test_cli.py`, `tests/test_reporting.py`
  - `ruff --select I,F` OK sur `tests/test_workflow.py`
  - `ruff --select I,F src tests` OK
  - `git diff --check` OK

### 2026-05-06 - Passe 35 : garde-fou responsive contre sections desktop residuelles

- declencheur :
  - captures tablette/mobile montrant des pages reduites en colonne trop etroite a gauche
  - cause mesuree : des sections desktop de `1920px` restaient visibles dans des breakpoints `834px` / `402px`
  - le runtime `page-shell` utilisait cette largeur residuelle pour calculer le scale global
- correction CSS dans `src/figma2hugo/generators/css/generator.py` :
  - les sections / containers avec `class_name` mais sans `kind` explicite sont maintenant masques quand ils sont absents du breakpoint courant
  - les backgrounds restent proteges par la logique dediee aux assets de fond
- correction runtime dans `templates/shared/page-shell.js` :
  - le calcul de scale utilise la largeur active du breakpoint (`--page-max-width`)
  - les bounds visibles continuent a servir a proteger la hauteur
  - une section visible trop large ne peut plus reduire toute la page
- validation navigateur post-correctif :
  - `page-prestation-2` / `page-prestation-3` a `768px` :
    - ancien scale mesure : environ `0.4`
    - nouveau scale : `0.920863309352518`
  - `page-prestation-2` / `page-prestation-3` a `390px` :
    - ancien scale mesure : environ `0.203125`
    - nouveau scale : `0.9701492537313433`
  - les premieres sections prennent maintenant toute la largeur viewport
- validation reelle :
  - build tolerant 5 pages relance via `--page-file`
  - `figma2hugo validate .figma2hugo-scratch/real-figma/site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - overflow horizontal : `0`
  - images cassees : `0`
  - warnings interactions : `0`
- regressions ajoutees :
  - une section top-level absente d'un breakpoint est masquee
  - `page-shell.js` ignore les sections trop larges pour le scale et garde les bounds visibles pour la hauteur
- regressions executees :
  - ciblage generateurs : `2 passed`
  - ciblage responsive/validator/integration reelle : `19 passed`
  - suite complete : `228 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F` OK sur `src/figma2hugo/generators/css/generator.py`, `templates`, `tests/test_generators.py`

### 2026-05-06 - Passe 36 : garde-fou anti-chevauchement responsive

- declencheur :
  - captures mobile/tablette avec superpositions de titres, textes, CTA et FAQ
  - mesure Playwright initiale sur la sortie reelle :
    - `page-prestation-2` mobile : hero / accompagnement + FAQ
    - `page-prestation-2` tablette : titre H4 / texte + CTA
    - `page-prestation-3` mobile/tablette : variantes du meme probleme
- correction CSS dans `src/figma2hugo/generators/css/generator.py` :
  - ajout de variables runtime non intrusives :
    - `--page-section-stack-shift`
    - `--content-node-stack-shift`
    - `--content-text-stack-shift`
  - les shifts valent `0px` par defaut
- correction runtime dans `templates/shared/page-shell.js` :
  - reparation activee uniquement pour les shells fixes responsives (`pageWidth <= 1024`)
  - empilement des sections visibles directes, y compris les headers avant le `<main>`
  - mesure des contenus visibles debordants pour pousser les sections suivantes
  - detection locale des collisions texte/texte
  - detection par section des collisions entre contenus distincts
  - deplacement d'un conteneur complet quand le texte appartient a un bouton ou a un panneau FAQ
  - conservation du plus grand shift calcule pour eviter qu'une passe secondaire annule une correction locale
- validation navigateur post-correctif :
  - `page-prestation-2` mobile `390px` : `0` chevauchement, `0` erreur JS
  - `page-prestation-2` tablette `768px` : `0` chevauchement, `0` erreur JS
  - `page-prestation-3` mobile `390px` : `0` chevauchement, `0` erreur JS
  - `page-prestation-3` tablette `768px` : `0` chevauchement, `0` erreur JS
  - `page-etude-de-cas` mobile/tablette : `0` chevauchement
  - `page-a-propos` mobile/tablette : `0` chevauchement
- validation reelle :
  - build tolerant 5 pages relance via `--page-file`
  - `figma2hugo validate .figma2hugo-scratch/real-figma/site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - viewports responsive avec issues : `0 / 30`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
- regressions ajustees :
  - CSS du shell fixe verifie les variables de shift section/node/text
  - `page-shell.js` verifie les reparations anti-collisions et l'empilement responsive
- regressions executees :
  - ciblage generateurs : `1 passed`
  - ciblage responsive/validator/integration reelle : `19 passed`
  - suite complete : `228 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F` OK sur `src/figma2hugo/generators/css/generator.py`, `tests/test_generators.py`

### 2026-05-06 - Passe 37 : correction breakpoints, overlays tablette et rognage

- declencheur :
  - mobile : bande/padding residuel a droite sur des viewports plus larges que la frame Figma 402px
  - tablette : superpositions residuelles dans FAQ et grilles de cas clients
  - besoin de proteger les petits depassements de frame visibles sans corriger aveuglement la maquette
- correction breakpoints dans `src/figma2hugo/generators/css/generator.py` :
  - les variantes mobiles `390/402px` couvrent maintenant `max-width: 480px`
  - les variantes tablettes `834px` couvrent maintenant `max-width: 1024px`
  - le shell fixe responsive peut upscale la frame active pour remplir le viewport
- correction markup dans `src/figma2hugo/generators/_shared.py` :
  - les conteneurs interactifs imbriques dans un autre interactif sont demotes en `<div>`
  - cas reel traite : variantes mobile de trigger FAQ qui produisaient auparavant des `button` imbriques
- correction CSS composants :
  - `templates/hugo/assets/css/components/accordion.css` baisse la specificite via `:where(...)`
  - `templates/hugo/assets/css/components/link-grid.css` baisse aussi la specificite via `:where(...)`
  - les geometries Figma fixes gagnent donc face aux helpers responsive generiques
- protection runtime dans `templates/shared/page-shell.js` :
  - la largeur effective tient compte des textes et assets de contenu visibles qui debordent legerement
  - les fonds/decoratifs et wrappers structurels sont exclus pour ne pas reduire toute la page
- validation navigateur post-correctif :
  - pages mesurees : `page-a-propos`, `page-etude-de-cas`, `page-mentions-legales`, `page-prestation-2`, `page-prestation-3`
  - viewports mesures : `390`, `414`, `480`, `768`, `834`, `1024`
  - `30 / 30` mesures : `scrollWidth == viewport`
  - `30 / 30` mesures : `0` chevauchement texte
  - `30 / 30` mesures : `0` overflow horizontal significatif
  - `page-prestation-2/3` : FAQ tablette et grilles cas clients sans superposition mesuree
  - `page-mentions-legales` mobile : petit depassement d'image protege sans shrink global
- validation reelle :
  - build tolerant 5 pages via `--page-file`
  - `figma2hugo validate .figma2hugo-scratch/real-figma/site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - viewports responsive avec issues : `0 / 30`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
- regressions executees :
  - ciblage page shell / responsive / accordion / link-grid : `17 passed`
  - suite complete : `228 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-06 - Passe 38 : rich-text responsive et chevauchements page accueil

- declencheur :
  - capture utilisateur sur `page-accueil` montrant un chevauchement dans `Notre accompagnement`
  - les validations precedentes etaient vertes sur le scratch multi-pages, mais pas sur la sortie locale `site/public/page-accueil`
  - cause racine : les variantes tablette retrecissaient les boites texte, tandis que les spans rich-text gardaient leurs styles inline desktop
- correction CSS dans `src/figma2hugo/generators/css/generator.py` :
  - emission de regles CSS pour les spans rich-text sous leur parent texte
  - ces regles utilisent `!important` afin que les media queries responsive puissent remplacer les styles inline desktop
  - ajout d'un fallback de `line-height` parent pour les textes segmentes, afin d'eviter la strut navigateur par defaut sur mobile
  - couverture ajoutee pour les overrides de typographie de segments en breakpoint tablette
- correction runtime dans `templates/shared/page-shell.js` :
  - les mesures anti-collision utilisent maintenant une boite visuelle etendue pour les textes en `overflow: visible`
  - `scrollHeight` / `scrollWidth` sont pris en compte quand le texte deborde reellement de sa boite CSS
  - les textes volontairement clipses en `overflow: hidden` ne poussent pas la mise en page
- sortie locale regeneree :
  - `site/assets/css/pages/page-accueil.css`
  - `site/assets/js/page-shell.js`
  - `site/public` via `hugo --source site --minify`
- validation navigateur post-correctif sur `site/public/page-accueil` :
  - viewports mesures : `390`, `402`, `414`, `480`, `768`, `834`, `1024`, `1200`, `1440`
  - `overlapCount=0` sur tous les viewports
  - `scrollWidth == viewport` sur tous les viewports
  - la zone `Notre accompagnement` ne superpose plus les titres H4, paragraphes et CTA
- validation CLI :
  - `figma2hugo validate site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions formulaire : OK
- regressions executees :
  - ciblage rich-text/page-shell : `4 passed`
  - suite complete : `230 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-06 - Passe 39 : largeur mobile, sauts de ligne Figma et decor tablette page accueil

- declencheur :
  - nouvelles captures utilisateur sur `site/public/page-accueil`
  - mobile : titre hero tasse/coupe, fond bleu qui ne remplissait pas toute la largeur, bande blanche a droite
  - tablette : grand blanc entre le hero et `Notre accompagnement`, cause par une decoration hero qui depassait du frame
- correction CSS dans `src/figma2hugo/generators/css/generator.py` :
  - ajout d'une normalisation des sauts de ligne Unicode Figma `U+2028` / `U+2029`
  - les titres contenant ces separators ne sont plus traites comme des single-line centres
  - cas corrige : le H1 mobile passe de `line-height: 74px` a son vrai `line-height: 30px`
  - les variantes responsive utilisent maintenant la largeur declaree du frame Figma pour `--page-max-width`
  - cas corrige : la variante mobile reste a `402px`, meme si une section historique a un extent plus large
- correction runtime dans `templates/shared/page-shell.js` :
  - les sections visibles continuent de proteger la hauteur, mais ne peuvent plus elargir la largeur effective
  - les boites texte ne peuvent elargir la page que si le texte deborde vraiment horizontalement (`scrollWidth > clientWidth`)
  - les assets decoratifs/background sont exclus du calcul d'empilement des sections
  - cas corrige : le decor gauche du hero tablette ne pousse plus `section-accompagnement` vers le bas
- tests de regression ajoutes :
  - separateur de ligne Unicode dans un titre centre
  - largeur declaree d'une variante responsive avec section plus large que la page
  - garde-fou page shell sur les assets non decoratifs, textes et stack de sections
- sortie locale regeneree :
  - `site/assets/css/pages/page-accueil.css`
  - `site/assets/js/page-shell.js`
  - `site/public` via `hugo --source site --minify`
- validation navigateur post-correctif sur `site/public/page-accueil` :
  - viewports mesures : `390`, `402`, `768`, `834`, `1024`, `1200`, `1440`
  - `scrollWidth == viewport` sur tous les viewports mesures
  - `overlapCount=0` sur tous les viewports mesures
  - mobile `402px` : hero `402px`, H1 `line-height: 30px`, gap hero/accompagnement `10px`
  - mobile `390px` : hero `390px`, scale `390 / 402`, aucune bande blanche a droite
  - tablette `834px` : gap hero/accompagnement ramene a environ `16px` au lieu du decalage par decor
- validation CLI :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions formulaire : OK
  - strict toujours non pret uniquement a cause des ambiguites Figma deja connues : `1` duplicate sibling token, `1` changement de texte a revoir
- regressions executees :
  - ciblage page-shell/responsive/H1 Unicode : `3 passed`
  - generateurs complets : `101 passed`
  - suite complete : `232 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-06 - Passe 40 : finition footer mobile et mini-formulaire

- declencheur :
  - capture utilisateur du bas de page mobile montrant le formulaire footer reduit a une taille non exploitable
  - symptome visible : placeholders HTML minuscules et icone rouge native de validation dans un panneau qui devrait rester visuel
- correction runtime dans `templates/shared/page-shell.js` :
  - ajout de `repairTinyResponsiveForms(page, scale)`
  - en layout responsive fixe, un formulaire visible de moins de `128px` de large est marque `data-page-shell-tiny-form="true"`
  - ses vrais controles HTML et son submit sont desactives pour eviter une interaction impossible
  - les controles HTML sont caches (`visibility: hidden`) afin de garder le graphisme Figma propre
  - les controles sont restaures automatiquement si un autre breakpoint repasse au-dessus du seuil
- validation visuelle :
  - capture locale `351px` bas de page : plus de placeholders minuscules ni d'icone rouge de validation
  - tablette `834px` : formulaire non marque tiny, controles visibles et actifs
- validation navigateur post-correctif :
  - viewports mesures : `351`, `390`, `402`, `768`, `834`, `1024`, `1200`, `1440`
  - `scrollWidth == viewport` sur tous les viewports mesures
  - `overlapCount=0` sur tous les viewports mesures
  - tiny form uniquement sur mobile (`351/390/402`), pas sur tablette/desktop
- validation CLI :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
  - formulaire desktop : `pass`
  - formulaire mobile : `skipped/not-visible`, attendu car le mini-formulaire est neutralise
- regressions executees :
  - ciblage page-shell : `1 passed`
  - generateurs complets : `101 passed`
  - suite complete : `232 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-06 - Passe 41 : espacement bouton / bandeau tablette

- declencheur :
  - retour utilisateur : en tablette, le bouton `Tous nos accompagnements` etait trop proche du bandeau bleu
- mesure avant correction :
  - `768px` : environ `0.9px` entre le bouton et le bandeau
  - `834px` : environ `1px` entre le bouton et le bandeau
  - desktop et mobile etaient deja plus aeres
- correction runtime dans `templates/shared/page-shell.js` :
  - ajout de `repairButtonBandSpacing(page, scale)`
  - en layout responsive fixe, les boutons non-submit gardent un espace minimal avec le prochain node/asset `bandeau` / `banner`
  - le decalage passe par `--content-node-stack-shift`, donc la pile de sections continue de se recalculer proprement ensuite
- validation navigateur post-correctif :
  - viewports mesures : `351`, `390`, `402`, `768`, `834`, `913`, `1024`, `1200`, `1440`
  - `scrollWidth == viewport` sur tous les viewports mesures
  - `overlapCount=0` sur tous les viewports mesures
  - ecart bouton/bandeau : `20.25px` a `768px`, `22px` a `834px`, `24.08px` a `913px`, `27.01px` a `1024px`
- validation CLI :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
- regressions executees :
  - generateurs complets : `101 passed`
  - suite complete : `232 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-06 - Passe 42 : finition tablette formulaire, Embedded et bandeau CTA

- declencheur :
  - nouvelles captures utilisateur tablette montrant :
    - formulaire contact trop petit avec placeholders HTML et icone native de validation visibles
    - controles `Le Labo` / `CIR` trop proches des paragraphes de la section Embedded
    - texte du bandeau CTA bleu legerement colle / rogne en bas
- correction runtime dans `templates/shared/page-shell.js` :
  - le seuil `repairTinyResponsiveForms` passe a `180px` Figma pour neutraliser aussi le mini-formulaire tablette
  - ajout de `repairPostTextControlSpacing(page, scale)` pour garantir un espace minimal entre textes longs et petits controles/assets suivants
  - ajout de `repairBandTextContainment(page, scale)` pour remonter les textes internes des bandeaux si la marge basse devient insuffisante
  - `setStackShift` sait maintenant piloter separement les nodes, textes et assets
- correction CSS dans `src/figma2hugo/generators/css/generator.py` :
  - les assets recoivent `--content-asset-stack-shift`, ce qui permet de deplacer proprement des petits visuels comme le logo `CIR`
- sortie locale regeneree :
  - `site/assets/css/pages/page-accueil.css`
  - `site/assets/js/page-shell.js`
  - `site/public` via `hugo --source site --minify`
- validation navigateur ciblee tablette :
  - viewports mesures : `768`, `834`, `913`, `1024`
  - formulaire contact marque `tiny`, controles HTML caches et desactives
  - ecart bouton/bandeau CTA maintenu a `22px`
  - marge basse minimale des textes de bandeau : `8px`
  - ecarts Embedded :
    - `Le Labo` apres paragraphe : `18px` a `768/834/913`, `20.21px` a `1024`
    - `CIR` apres paragraphe : `18px` a `768/834/913`, `20.21px` a `1024`
- validation navigateur transverse :
  - viewports mesures : `351`, `390`, `402`, `768`, `834`, `913`, `1024`, `1200`, `1440`
  - `scrollWidth == viewport` sur tous les viewports mesures
  - mini-formulaire neutralise sur les rendus compacts, restaure sur desktop
- validation CLI :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
  - strict toujours non pret uniquement a cause des ambiguites Figma deja connues : `1` duplicate sibling token, `1` changement de texte a revoir
- regressions executees :
  - generateurs complets : `101 passed`
  - suite complete : `232 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-06 - Passe 43 : correction visuelle bandeau CTA et bouton Le Labo tablette

- declencheur :
  - retour utilisateur : texte du bandeau bleu encore trop bas et bouton `Le Labo` visuellement etrange sur tablette
- correction runtime dans `templates/shared/page-shell.js` :
  - `repairBandTextContainment` impose maintenant `20px` de marge basse brute dans les bandeaux responsive fixes, au lieu de seulement eviter le rognage
  - ajout de `repairBreakpointBackgroundLayers(page)` :
    - regroupe les fonds decoratifs `asset-bg-*` par parent
    - quand un fond breakpoint (`-w834`, `-w402`, etc.) est visible, masque le fond base equivalent
    - conserve uniquement la variante visible la plus specifique
  - cas corrige : `node-button-labo-embedded` n'affiche plus simultanement le fond desktop et le fond tablette
- sortie locale regeneree :
  - `site/assets/css/pages/page-accueil.css`
  - `site/assets/js/page-shell.js`
  - `site/public` via `hugo --source site --minify`
- validation navigateur ciblee :
  - viewports mesures : `351`, `390`, `402`, `768`, `834`, `913`, `1024`, `1200`, `1440`
  - `scrollWidth == viewport` sur tous les viewports mesures
  - tablette `768/834/913/1024` :
    - marge basse minimale des textes du bandeau CTA : `20px`
    - marge haute minimale : `14.75px`
    - un seul fond actif dans le bouton `Le Labo`
    - fond base du bouton masque par `data-page-shell-hidden-breakpoint-bg`
- validation CLI :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
  - strict toujours non pret uniquement a cause des ambiguites Figma deja connues
- regressions executees :
  - ciblage page-shell : `1 passed`
  - generateurs complets : `101 passed`
  - suite complete : `232 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-06 - Passe 44 : audit genericite process et idiome Hugo

- declencheur :
  - demande utilisateur : enorme passe de verification de genericite du process et de correspondance a l'idiome Hugo
- verification de genericite :
  - audit `src/` + `templates/` contre les noms de la maquette courante (`page-accueil`, `Le Labo`, `Bastien Blochet`, `Embedded In Mind`, ids Figma courants, etc.)
  - resultat : aucun couplage page/client detecte dans le moteur ou les templates
  - les mentions restantes sont limitees aux docs, fixtures de test et sortie generee
  - ajout d'un test d'hygiene pour bloquer toute reintroduction de ces noms dans `src/` ou `templates/`
- verification idiome Hugo :
  - confirme que `resolve_page_data.html` utilise bien `hugo.Data`, recommande par Hugo moderne
  - tentative controlee de retour a `site.Data` rejetee : Hugo `0.160.1` signale que `.Site.Data` est deprecie depuis `0.156.0`
  - refactor de `templates/hugo/layouts/_default/baseof.html` :
    - listes `slice` pour les CSS communs et JS communs
    - conservation du pipeline Hugo `resources.Get -> minify -> fingerprint`
    - ajout dynamique de `.Params.stylesheet` dans la liste des CSS
  - mise a jour du partial genere local `site/layouts/_default/baseof.html`
- robustesse front matter :
  - correction de `_escape_front_matter_string`
  - les guillemets, antislashs, `CRLF`, `CR` et sauts de ligne sont maintenant echappes proprement dans le YAML Hugo
  - test ajoute avec un titre de page contenant guillemets, saut de ligne et antislash
- smoke-test Hugo generique :
  - generation d'un mini-site multi-pages arbitraire, sans lien avec `page-accueil`
  - pages generees : `services-r-d-1440`, `journal-lab-2026`
  - routes publiques : `services-r-d-1440/`, `journal-lab-2026/`
  - donnees : `data/pages/services-r-d-1440.json`, `data/pages/journal-lab-2026.json`
  - CSS : `assets/css/pages/services-r-d-1440.css`, `assets/css/pages/journal-lab-2026.css`
  - build Hugo reel OK
- validation locale `site` :
  - `hugo --source site --minify` OK
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - textes manquants : `0`
  - assets manquants : `0`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
  - strict toujours non pret uniquement a cause des ambiguites Figma deja connues
- regressions executees :
  - generateurs complets : `102 passed`
  - hygiene repo : `2 passed`
  - suite complete : `234 passed, 1 skipped`
- lint :
  - `ruff --select I,F src tests` OK
  - `ruff check src tests` non vert hors perimetre immediat : dette existante majoritairement `E501` sur de nombreux fichiers, plus quelques modernisations `UP`

### 2026-05-06 - Passe 45 : bandeau icones tablette

- declencheur :
  - capture utilisateur tablette du bandeau `Vos idees + Notre expertise = Notre aventure`
  - symptome : les libelles etaient remontes dans les pictogrammes
- cause :
  - `repairBandTextContainment` protegeait bien les grands bandeaux, mais s'appliquait aussi aux petites cartes internes `card-bandeau-item-*`
  - ces cartes etaient traitees comme des bandeaux, donc leurs labels etaient remontes d'environ `20px`
- correction runtime dans `templates/shared/page-shell.js` :
  - ajout de `isCardLikeBandItem(element)` pour exclure les petites cartes/items de `repairBandTextContainment`
  - ajout de `repairIconLabelCards(page, scale)` pour garantir un espace minimal icon -> label dans les cartes de bandeau
  - ajout de `addTextShift(text, delta)` pour corriger finement un label deja positionne sans toucher au node complet
- sortie locale regeneree :
  - `site/assets/js/page-shell.js`
  - `site/assets/css/pages/page-accueil.css`
  - `site/public` via `hugo --source site --minify`
- validation navigateur ciblee tablette :
  - viewports mesures : `768`, `834`, `913`, `1024`
  - `scrollWidth == viewport` sur tous les viewports mesures
  - ecarts icon -> label :
    - `Vos idees` : `7px`
    - `Notre expertise` : `10.86px`
    - `Notre aventure` : `7px`
- validation CLI :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
- regressions executees :
  - ciblage page-shell : `1 passed`
  - generateurs complets : `102 passed`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-07 - Passe 46 : dedup backgrounds responsive contact/footer

- declencheur :
  - captures utilisateur sur les derniers reglages responsive de la zone contact/footer
  - besoin de proteger les fonds responsives contre les superpositions et les restes hors cadre
- mesure locale :
  - viewports controles : `351`, `402`, `768`, `834`, `1024`, `1200`
  - le footer rendu local collait deja correctement au bandeau contact
  - la mesure a revele un probleme generique plus discret :
    - les backgrounds responsives sous `.page-section__inner` n'etaient pas dedupliques
    - seuls les tokens `asset-bg-*` etaient reconnus
    - les fonds de champs `asset-zone-*` pouvaient donc rester doubles selon le breakpoint
- correction runtime dans `templates/shared/page-shell.js` :
  - `repairBreakpointBackgroundLayers` inspecte maintenant aussi `.page-section__inner`
  - la cle de deduplication s'appuie sur toute classe `asset-*` decorative avec suffixes `-w...`
  - ajout de `breakpointBackgroundClass(element)` pour reutiliser la meme logique dans la cle et le score de variante
- sortie locale regeneree :
  - `site/assets/js/page-shell.js`
  - `site/public` via `hugo --source site --minify`
- validation navigateur ciblee :
  - viewports controles : `402`, `834`, `1024`
  - doublons visibles de backgrounds responsives : `0`
  - `scrollWidth == viewport` sur tous les viewports controles
  - bandeau contact et strip footer jointifs sur mobile/tablette
- validation CLI :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
  - strict toujours non pret uniquement a cause des ambiguites Figma deja connues
- regressions executees :
  - generateurs complets : `102 passed`
  - suite complete : `234 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-07 - Passe 47 : composants repetitifs detectes

- objectif :
  - generaliser le traitement des groupes de composants repetes sans dependre de noms Figma trop specifiques
  - distinguer une vraie ambiguite responsive d'une collection repetitive structurellement coherente
- detection structurelle ajoutee dans `src/figma2hugo/generators/_shared.py` :
  - signature de composant repetitif basee sur les enfants directs :
    - roles de textes regroupes par buckets (`heading`, `body`, `label`, etc.)
    - assets regroupes par usage (`background`, `decorative`, `media`, `icon`, etc.)
    - conteneurs imbriques regroupes par role semantique
  - verification de compatibilite de taille entre items siblings
  - exclusion des familles interactives deja dediees : accordions, carousel, form, field, nav, header, footer, boutons
- annotation canonique :
  - parent de collection :
    - `data-component-list="true"`
    - `data-repeat-group`
    - `data-repeat-count`
  - items repetes :
    - `data-component-item="true"`
    - `data-repeat-group`
    - `data-repeat-index`
  - items generiques repetes promus en `role="card"` avec `data-card="true"` et tag `article` quand le tag initial est neutre
- idiome Hugo :
  - ajout du partial gere `layouts/partials/components/component-list.html`
  - ajout de `assets/css/components/component-list.css`
  - inclusion du CSS commun dans `templates/hugo/layouts/_default/baseof.html`
  - `HugoGenerator` route les noeuds `data-component-list` vers le partial `components/component-list.html`
- merge responsive :
  - `src/figma2hugo/generators/_responsive.py` reconnait maintenant les tokens siblings repetes qui forment une collection structurelle
  - en strict, ces tokens ne sont plus des blockers si la repetition est coherente
  - nouveau warning informatif :
    - `Responsive variant ... treats repeated sibling token ... as a repeated component group ...`
- validation / reporting :
  - nouveau type d'issue responsive : `repeated-component-token`
  - severite : `info`
  - nouveau compteur : `repeatedComponentTokenCount`
  - `responsive-audit.md` affiche une section `Composants repetitifs detectes`
  - la matrice de support mentionne maintenant `component-list` parmi les composants opt-in responsives
- sortie locale :
  - scaffold synchronise dans `site` :
    - `site/layouts/_default/baseof.html`
    - `site/layouts/partials/components/component-list.html`
    - `site/assets/css/components/component-list.css`
  - `site/public` regenere via `hugo --source site --minify`
- validation locale :
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - `buildOk=true`
  - viewports responsive avec issues : `0 / 6`
  - overflow horizontal : `0`
  - images cassees : `0`
  - interactions en echec : `0`
  - note : le JSON local `site/data/pages/page-accueil.json` n'a pas ete re-extrait depuis Figma, il conserve donc l'ancien warning strict sur `card-v-texte`; la nouvelle classification s'appliquera a la prochaine generation complete
- regressions executees :
  - suite complete : `236 passed, 1 skipped`
- controle statique :
  - `ruff --select I,F src tests` OK

### 2026-05-07 - Passe 48 : reconciliation geometrique amont

- declencheur :
  - besoin de gerer dimensions, emplacements et logiques positionnelles plus tot que les reparations navigateur
  - objectif : exploiter les bounds Figma exportes pour deduire des flows coherents quand la structure le permet
- implementation dans `src/figma2hugo/generators/_shared.py` :
  - ajout d'une passe `geometry reconciliation` apres la detection des composants repetitifs
  - conservation des bounds Figma auteur dans `metadata.authoredBounds` lorsque le canonique resserre un conteneur autour de ses enfants
  - inference prudente :
    - axe `row`, `column` ou `grid`
    - gap principal et cross-gap
    - padding top/right/bottom/left
    - confiance de detection
  - activation du flow uniquement pour les cas controles :
    - collections `component-list`
    - conteneurs nommes comme des blocs de layout (`row-*`, `grid-*`, `stack-*`, `split-*`, `section-block-*`, etc.)
    - layouts deja explicitement flow
  - annotation des enfants avec ancres et politiques de taille :
    - `data-position-x`
    - `data-position-y`
    - `data-size-x`
    - `data-size-y`
- schema / validation :
  - `LayoutMetadata` expose maintenant les champs de reconciliation :
    - `geometrySource`, `geometryAxis`, `geometryConfidence`
    - `positionAnchorHorizontal`, `positionAnchorVertical`
    - `sizePolicyHorizontal`, `sizePolicyVertical`
    - marges derivees
  - matrice de support mise a jour : l'inference reste limitee aux familles de composants supportees
- idiome Hugo :
  - pas de correction aveugle dans le navigateur
  - les donnees enrichies restent dans le JSON canonique
  - les partials et CSS existants (`component-list`, `section-block`) consomment les attributs `data-layout-*`
- validation ciblee :
  - `PYTHONPATH=src python -m pytest tests/test_generators.py -k "geometry_flow or repeated_component_groups" -q`
  - resultat : `2 passed`
- validation globale :
  - `PYTHONPATH=src python -m pytest -p no:cacheprovider`
  - resultat : `237 passed, 1 skipped`
  - `PYTHONPATH=src python -m ruff check --select I,F src tests`
  - resultat : OK
  - `PYTHONPATH=src python -m figma2hugo.cli validate site`
  - resultat : `buildOk=true`, `0 / 6` viewports avec issues, `strictReady=true` sur la famille locale

## Points Ouverts

- la couverture "responsive complet" n'est pas encore synonyme de "toute page absolue Figma devient automatiquement fluide"
- le merge est maintenant mieux protege, mais le workflow Figma doit encore rester rigoureux sur les noms et la structure
- des siblings avec exactement le meme nom/token sont maintenant detectes, comptes et bloquables en mode strict, mais les exports par defaut restent tolerants tant que les maquettes historiques ne sont pas renommees
- la validation Playwright reelle est verte sur les 5 pages fournies, en mode tolerant, mais 3 familles ne sont pas strict-ready
- les differences de textes entre breakpoints sont maintenant comptees et listees dans `responsive-audit.md` : il faut confirmer si ce sont des variantes volontaires ou des divergences de maquette
- la factorisation transverse progresse ; les prochaines cibles restent le decoupage fin de la GUI et la suite du rendu post-canonique partage
- prochaine validation manuelle conseillee :
  - creer un fichier local `.figma2hugo-scratch/real-figma/pages.txt`
  - y placer les URLs Figma a tester, une par ligne
  - lancer `figma2hugo build-site .figma2hugo-scratch/real-figma/site --page-file .figma2hugo-scratch/real-figma/pages.txt`
  - activer le strict si l'objectif est de bloquer toute ambiguite : ajouter `--strict-responsive-matching`
  - puis `figma2hugo validate .figma2hugo-scratch/real-figma/site`
