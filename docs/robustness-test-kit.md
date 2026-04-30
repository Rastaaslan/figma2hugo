# Kit De Robustesse

Ce kit sert a preparer un **crash test Figma -> convertisseur -> validation** avec le moins de manipulation possible.

## Fichiers Importables

- `crash-test-importable-1920.svg`
- `crash-test-importable-1280.svg`
- `crash-test-importable-1024.svg`
- `crash-test-importable-768.svg`
- `crash-test-importable-390.svg`

Chaque fichier contient deja :

- une page nommee `page-crash-test-<largeur>`
- les sections `hero`, `prestation`, `cards`, `faq`, `carousel`, `contact`, `footer`
- les noms de composants attendus par le moteur
- des textes techniques utiles :
  - `href-*`
  - `action-contact`
  - `option-*`
  - `placeholder-*`

## Usage Recommande

1. Importer **un SVG par breakpoint** dans Figma.
2. Verifier que les groupes gardent bien leurs noms principaux.
3. Si Figma a ecrase un nom, le corriger une fois dans Figma.
4. Lancer ensuite le convertisseur sur le node cible.

## Limite A Connaitre

Un SVG importe dans Figma sous forme de groupes et de layers, pas comme de vrais `Frame` ou `Auto Layout`.

Donc ce kit est excellent pour :

- la robustesse d'extraction
- la preservation des noms
- la generation HTML/CSS/Hugo
- la validation des composants reconnus par naming

Mais si vous voulez un test **100% fidele au futur responsive automatise**, il faudra ensuite refaire la version canonique directement en vrais frames Figma.

## Conseil Pratique

Pour votre campagne de robustesse :

- commencez par `crash-test-importable-1920.svg`
- si le run est propre, importez ensuite `1280`, `1024`, `768`, `390`
- gardez les memes noms de sections et de composants entre variantes

## Validation Attendue

Le kit est utile si, apres generation et validation, vous obtenez :

- `buildOk = true`
- pas de `missingAssets`
- pas de `missingTexts`
- `responsive.checked = true`
- `interactions.checked = true`

Et visuellement :

- FAQ clickable
- `href-card` clickable
- carousel clickable
- formulaire visible avec placeholders
