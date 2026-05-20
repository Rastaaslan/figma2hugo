# Notice Utilisateur Et Technique pipeline

Cette notice explique comment utiliser le pipeline de `figma2hugo`, comment
preparer Figma, comment generer Hugo et comment valider le resultat avec les
baselines.

## Pour Qui

- Utilisateur Figma : prepare les pages et les noms de calques.
- Integrateur : lance la generation Hugo et regarde les rapports.
- Developpeur : maintient le pipeline, les baselines et le release gate.

## Idee Generale

Le pipeline transforme une ou plusieurs URLs Figma en site Hugo.

```text
Figma -> raw JSON -> normalisation pipeline -> render plan -> Hugo -> smoke visuel -> gate
```

Figma reste la source de verite pour le contenu, la structure, les breakpoints
et l'intention visuelle. Une baseline n'est pas Figma lui-meme : c'est un rendu
navigateur approuve apres generation depuis Figma.

Exception importante : les composants web interactifs doivent rester utilisables
dans le navigateur. Les formulaires, accordions, carrousels, link cards et
controles equivalents peuvent donc recevoir des ajustements HTML/CSS bornes,
documentes dans le rapport, quand la geometrie Figma serait fidele mais
inutilisable.

## Preparer Figma

Les frames de page doivent suivre :

```text
page-<slug>-1920
page-<slug>-834
page-<slug>-402
```

Exemple :

```text
page-dashboard-1920
page-dashboard-834
page-dashboard-402
```

Les blocs internes doivent utiliser une structure stable :

```text
region-dashboard-main
  toolbar-filtres
  table-commandes

section-contact
  form-contact

modal-confirm-delete
  button-cancel
  button-confirm
```

Reference complete : `docs/figma-page-architecture-reference.md`.
Reference debug : `docs/debug-function-map.md`.

## Generer Depuis L'UI

1. Ouvrir l'UI.
2. Coller une ou plusieurs URLs Figma.
3. Choisir le dossier de destination.
4. Renseigner un token Figma si necessaire.
5. Cliquer sur `Generer Hugo`.

Le bouton `Generer Hugo` :

- utilise le pipeline ;
- force le rafraichissement des donnees Figma ;
- ecrit un site Hugo dans le dossier cible ;
- planifie les references visuelles Figma a partir des nodes source ;
- lance un smoke visuel ;
- cherche une baseline visuelle projet ;
- si aucune baseline projet n'existe, exporte les PNG Figma et compare le rendu
  Hugo a ces references ;
- cherche un contrat responsive projet.

Si aucune baseline visuelle n'existe pour ce projet, l'UI propose de valider la
baseline apres generation. Le premier passage n'est donc plus aveugle : le
smoke utilise Figma comme reference visuelle quand c'est possible, puis la
baseline projet sert de reference approuvee pour les runs suivants.

## Generer Depuis La CLI

```powershell
$env:PYTHONPATH='src'
python -m figma2hugo.cli build-site site --page-file pages.txt --refresh-cache
```

`pages.txt` contient une URL Figma par ligne.

Pour utiliser un contrat responsive projet :

```powershell
python -m figma2hugo.cli build-site site --page-file pages.txt --responsive-contract-root baselines\review\pipeline\projects
```

## Baseline Visuelle

Une baseline visuelle est un ensemble de captures PNG du site genere, validees
comme rendu attendu.

Elle sert a detecter les regressions visuelles :

```text
nouveau rendu Hugo vs captures approuvees
```

Ordre de comparaison du smoke :

```text
1. baseline projet approuvee si disponible
2. reference PNG exportee depuis Figma si aucune baseline projet n'existe
3. capture seule si aucune reference Figma n'est disponible
```

Workflow :

```powershell
$env:PYTHONPATH='src'
python -m figma2hugo.cli visual-smoke site --out site-smoke --baseline-mode auto --baseline-root baselines\visual\pipeline\projects
python -m figma2hugo.cli promote-visual-baseline site-smoke --baseline-root baselines\visual\pipeline\projects --label first-approved
python -m figma2hugo.cli visual-smoke site --out site-smoke-compare --baseline-mode compare --baseline-root baselines\visual\pipeline\projects
```

Emplacement :

```text
baselines/visual/pipeline/projects/<project-id>/<snapshot-id>/
```

Statuts possibles :

```text
capture-only          capture sans comparaison
missing-baseline      capture attendue absente
pass                  rendu identique ou dans la tolerance
height-delta-review   hauteur differente a relire
review                diff visuel a relire
fail                  diff visuel bloquant
```

## Baseline Review Et Contrat Responsive

Une baseline review/contrat responsive liste les signaux intentionnels acceptes.
Elle ne modifie pas le HTML, le CSS ou Hugo. Elle change seulement la
classification de certains signaux :

```text
actionable-review -> accepted-contract
```

Promotion :

```powershell
python -m figma2hugo.cli promote-review-baseline site --baseline-root baselines\review\pipeline\projects --label first-approved
```

Utilisation :

```powershell
python -m figma2hugo.cli build-site site --page-file pages.txt --responsive-contract-root baselines\review\pipeline\projects
```

Emplacement :

```text
baselines/review/pipeline/projects/<project-id>/<snapshot-id>.json
```

Le matching est strict. Si Figma change et qu'un ancien contrat ne correspond
plus, le gate doit le signaler.

## Release Gate

Le release gate est la verification stricte avant de considerer une generation
comme livrable.

Exemple complet :

```powershell
$env:PYTHONPATH='src'
python scripts\release_gate.py .figma2hugo-scratch\release-project --page-file pages.txt --cache-dir .figma2hugo-scratch\pipeline-raw-cache --smoke-out .figma2hugo-scratch\release-project-smoke --widths 1920,1440,1280,1024,834,402 --screenshot-widths 1920,1440,1280,1024,834,402 --baseline-mode compare --baseline-root baselines\visual\pipeline\projects --review-baseline-root baselines\review\pipeline\projects --responsive-contract-root baselines\review\pipeline\projects --diff-review-threshold 0.002 --diff-fail-threshold 0.01
```

Le gate doit etre vert sur ces points :

- site genere en pipeline `pipeline` ;
- au moins une page ;
- `diagnostics.issueCount = 0` ;
- `responsive.issueCount = 0` ;
- aucun `blocking` ;
- aucun `P0` ou `P1` ;
- aucun `actionable-review` non approuve ;
- smoke `issueCount = 0` ;
- smoke `errorCount = 0` ;
- smoke `warnCount = 0` ;
- en mode compare, toutes les captures visuelles sont `pass`.

## Quand Figma Change

Si Figma change volontairement :

1. Regenerer Hugo avec `--refresh-cache`.
2. Relire le rendu navigateur.
3. Relire le rapport `report.json`.
4. Si le rendu est correct, promouvoir une nouvelle baseline visuelle.
5. Si les signaux responsive sont intentionnels, promouvoir une nouvelle
   baseline review.
6. Relancer le release gate strict.

Ne pas promouvoir une baseline pour cacher une erreur. Une baseline doit
representer un etat approuve.

## Sortie Hugo

Le pipeline conserve l'idiome Hugo :

```text
content/
data/pipeline/
layouts/
layouts/partials/pipeline/
assets/css/pipeline/
static/pipeline-assets/
```

Les ajustements semantiques pipeline doivent rester bornes, deterministes et visibles
dans les rapports.

## Rapports Importants

```text
site/report.json
site/.figma2hugo-pipeline-debug/diagnostics.json
site/.figma2hugo-pipeline-debug/*.render-plan.json
site-smoke/report.json
site-smoke/issues.json
site-smoke/review.html
```

Dans `site/report.json`, les blocs importants sont :

```text
sourceIdentity       identite stable du projet et hash de source
diagnostics          problemes de generation/layout
responsive           signaux responsive
review               classification des signaux
performance          temps des phases
cache                stats de cache raw/assets
```

## Glossaire

- Source Figma : design d'origine.
- Rendu Hugo : site genere et affiche par le navigateur.
- Baseline visuelle : captures approuvees du rendu Hugo.
- Baseline review : liste de signaux de review acceptes.
- Contrat responsive : declarations strictes de variantes responsive
  intentionnelles.
- Gate : verification automatique qui bloque les regressions.
- `projectId` : identifiant stable du projet, derive des sources Figma.
- `sourceHash` : hash qui change quand le contenu source change.

## Depannage

Si la generation ne voit pas une modification Figma :

- verifier que `--refresh-cache` est utilise ;
- dans l'UI, `Generer Hugo` force deja ce rafraichissement ;
- verifier que l'URL pointe vers le bon `node-id`.

Si le gate signale une diff visuelle :

- ouvrir `site-smoke/review.html` ;
- comparer les PNG generes et la baseline ;
- corriger Figma ou le pipeline si c'est une regression ;
- promouvoir une nouvelle baseline seulement si le nouveau rendu est attendu.

Si le gate signale un contrat responsive stale :

- ouvrir `site/report.json` ;
- regarder `review.responsiveContract.unusedDeclarations` ;
- supprimer ou regenerer la declaration qui ne matche plus.

Si un bloc n'est pas reconnu :

- verifier le nom du frame : `region-*`, `section-*`, `header`, `footer` ;
- verifier que le frame a une taille et une position coherentes ;
- verifier que les enfants ne changent pas de nom entre breakpoints sans raison.



