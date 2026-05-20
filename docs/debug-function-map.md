# Debug Function Map pipeline

Ce document aide a deboguer le pipeline. Il liste les fichiers importants,
les fonctions/classes a connaitre, leur role, et les premiers artifacts a
ouvrir selon le symptome.

Il ne remplace pas le code. Si une fonction manque, regenerer la liste brute :

```powershell
rg -n "^(def|class) " src\figma2hugo\pipeline src\figma2hugo\cli.py src\figma2hugo\gui.py src\figma2hugo\gui_presenter.py scripts\release_gate.py
```

## Point D'Entree Debug

Avant de lire le code, ouvrir ces fichiers de sortie :

```text
site/report.json
site/.figma2hugo-pipeline-debug/diagnostics.json
site/.figma2hugo-pipeline-debug/*.render-plan.json
site/.figma2hugo-pipeline-debug/*responsive-manifest.json
site/report.json -> figmaReference
site-smoke/report.json
site-smoke/issues.json
site-smoke/review.html
site-smoke/figma-reference/manifest.json
baselines/visual/pipeline/projects/<project-id>/index.json
baselines/review/pipeline/projects/<project-id>/index.json
```

Lecture rapide :

- `sourceIdentity` : verifier `projectId`, `sourceHash`, `figmaNodeIds`.
- `diagnostics.issueCount` : problemes de generation/layout.
- `responsive.issueCount` : problemes responsive bloquants.
- `review.byClassification` : `blocking`, `actionable-review`,
  `accepted-info`, `accepted-contract`.
- `review.responsiveContract` : declarations matchees, invalides ou stale.
- `visualReview.byStatus` : etat des diffs visuels.
- `visualReview.comparisonKind` : `visual-baseline`, `figma-reference` ou
  `capture`.
- `figmaReference` : plan ou export reel des references PNG Figma.
- `cache.raw` : savoir si la source vient du cache ou de Figma live.

## Arbre De Decision

```text
Figma non rafraichi
  -> cli.py / gui.py / runner.py
  -> verifier --refresh-cache et cache.raw

Node Figma absent ou mal lu
  -> fetcher.py / normalizer.py / models.py
  -> verifier raw JSON et sourceIdentity.sourceNodes

Region/section non reconnue
  -> normalizer.py
  -> verifier _infer_kind, _is_semantic_section_name, diagnostics no-section-candidates

Style ou composant incorrect
  -> render_plan.py
  -> verifier *.render-plan.json, component, attributes, style

Correction semantique inattendue
  -> semantic_adjustments.py
  -> verifier review.items et codes accepted-info

Overlap, gap ou contenu clippe
  -> diagnostics.py
  -> verifier diagnostics.json et report.review.items

Responsive incoherent
  -> responsive.py / review_contract.py / review_baselines.py
  -> verifier responsive-manifest.json et review.responsiveContract

Hugo ecrit un mauvais fichier
  -> hugo_renderer.py
  -> verifier content/, data/pipeline/, assets/css/pipeline/, managed-files.json

Diff visuel
  -> visual_smoke.py / visual_baselines.py
  -> ouvrir site-smoke/review.html et les PNG diff

Gate rouge
  -> scripts/release_gate.py
  -> lire checks[] dans la sortie JSON
```

## Flux Principal

```text
cli.py / gui.py
  -> runner.py
    -> fetcher.py
    -> normalizer.py
    -> render_plan.py
    -> semantic_adjustments.py
    -> diagnostics.py
    -> responsive.py
    -> review_contract.py / review_baselines.py
    -> hugo_renderer.py
    -> report.json
  -> visual_smoke.py
    -> visual_baselines.py
  -> release_gate.py
```

## CLI Et UI

### `src/figma2hugo/cli.py`

- `VisualBaselineMode` : enum `off`, `capture`, `compare`, `auto`.
- `_emit_json` : sortie JSON commune des commandes.
- `_parse_or_bad_parameter` : valide une URL Figma unique.
- `_parse_many_or_bad_parameter` : valide une liste d'URLs.
- `_read_page_file_urls` / `_split_page_url_text` : lisent `--page-file`.
- `build` : commande single-page, route vers pipeline par defaut.
- `build_site` : commande multi-page recommandee, accepte aussi `--raw`.
- `_run_build_site_command` : pont entre CLI user-facing et runner pipeline.
- `build_pipeline` : harness debug depuis raw JSON vers render plans/HTML/site/Hugo.
- `build_figma_pipeline` : harness debug depuis URLs Figma.
- `visual_smoke_pipeline` : lance le smoke visuel et les baselines.
- `promote_visual_baseline_pipeline` : promeut une capture visuelle approuvee.
- `promote_review_baseline_pipeline` : promeut les signaux review/contrats du
  `report.json`.
- `ui` : lance l'interface desktop.
- `report` / `validate` : commandes de lecture/validation generales.

Debug typique :

- Si une URL de `pages.txt` manque, regarder `_split_page_url_text`.
- Si un contrat projet n'est pas pris, verifier `--responsive-contract-root`
  dans `build_site`.

### `src/figma2hugo/gui.py`

- `Figma2HugoGUI` : fenetre Tkinter, etat UI, queue de progression.
- `_start_generation` : valide les inputs UI et demarre le thread.
- `_run_generation_job` : pose le token en env, lance la generation, renvoie
  succes/erreur dans la queue.
- `_poll_queue` : applique les retours UI, active le bouton baseline si besoin.
- `_run_generation_for_gui` : route Hugo vers pipeline et normalise le resultat UI.
- `_run_hugo_pipeline_generation` : build pipeline avec `refresh_cache=True`, contrat
  review projet, puis smoke visuel.
- `_run_visual_smoke_for_gui` : smoke auto avec baseline visuelle projet.
- `_default_visual_smoke_out` : dossier `destination-smoke`.
- `_default_visual_baseline_root` : `baselines/visual/pipeline/projects`.
- `_default_review_baseline_root` : `baselines/review/pipeline/projects`.
- `_gui_result_from_pipeline_hugo_payload` : normalise le payload pour l'UI.
- `_result_needs_baseline_promotion` : detecte le bootstrap visuel.
- `_promote_visual_baseline_for_gui` : promotion de baseline depuis l'UI.

Debug typique :

- Si l'UI ne voit pas la derniere modif Figma, verifier que
  `_run_hugo_pipeline_generation` passe `refresh_cache=True`.
- Si le bouton `Valider baseline` reste desactive, verifier
  `_result_needs_baseline_promotion` et `visualSmoke.visualReview`.

### `src/figma2hugo/gui_presenter.py`

- `GuiControlStates` : etats calcules des boutons.
- `has_figma_access` : detecte token/env/MCP.
- `clean_figma_urls` : nettoie les champs URL.
- `control_states` : active/desactive statique/Hugo selon running et nombre
  d'URLs.
- `figma_access_source` : texte d'origine de l'acces Figma.
- `selection_hint_message` : message d'aide selon nombre d'URLs.
- `format_generation_start` : log de lancement.
- `format_generation_success` : resume generation + smoke.
- `format_baseline_promotion_success` : resume promotion visuelle.
- `describe_generation_error` : classe une erreur pour l'UI.
- `split_generation_error` : extrait stage/cause/debug path.
- `looks_like_invalid_figma_url` : heuristique URL invalide.

Debug typique :

- Si le message UI est trompeur mais le build est bon, corriger ici plutot que
  dans le pipeline.

## Orchestration Et Build pipeline

### `src/figma2hugo/pipeline/runner.py`

- `build_pipeline_from_raw_files` : harness debug depuis raw JSON vers plans, HTML,
  static preview et Hugo preview.
- `build_pipeline_from_figma_urls` : meme harness apres fetch Figma.
- `build_pipeline_hugo_site_from_raw_files` : build final Hugo depuis raw.
- `build_pipeline_hugo_site_from_figma_urls` : build final Hugo depuis Figma.
- `_build_pipeline_hugo_site` : coeur de build final : normalisation, render plan,
  responsive, Hugo, report, cache.
- `_cached_or_fetch_raw_payload` : lit cache raw ou fetch Figma live.
- `_raw_cache_path` / `_resolved_raw_cache_dir` : emplacement du cache raw.
- `_empty_raw_cache_stats` / `_merge_raw_cache_stats` : stats cache.
- `_build_cache_report` : bloc `cache` du report.
- `_build_render_groups` : regroupe les variantes par famille responsive.
- `_expand_raw_payloads` / `_expand_raw_payload` : splitte un parent contenant
  plusieurs frames `page-<slug>-<width>`.
- `_looks_like_page_variant_root` : detecte les frames page top-level.
- `_propagate_link_card_hrefs` : reporte les hrefs de cartes liens entre
  variantes.
- `_write_responsive_manifests` : ecrit les manifests responsive debug.
- `_build_site_report` : assemble `report.json`.
- `_build_review_report` : construit `review.items`, groupes et compteurs.
- `_review_item` : normalise un signal diagnostic/responsive.
- `_classify_review_item` : decide `blocking`, `actionable-review`,
  `accepted-info`, `accepted-contract`.
- `_review_action` / `_review_owner` / `_review_priority` : tri de revue.
- `_is_blocking_responsive_issue` / `_is_blocking_pipeline_issue` : frontiere
  bloquant vs review.
- `_read_raw_json` : lit raw avec BOM tolerant.
- `_slug` / `_unique_slug` : slugs de fichiers.

Debug typique :

- Si `report.json` est mauvais, commencer par `_build_site_report`.
- Si une page parent n'est pas splittee, regarder `_expand_raw_payload`.
- Si un contrat responsive ne s'applique pas, verifier
  `responsive_contract_root` dans `_build_pipeline_hugo_site`.

### `src/figma2hugo/pipeline/orchestrator.py`

- `Pipeline.normalize` : wrapper vers `normalize_document`.
- `Pipeline.render_plan` : wrapper vers `build_render_plan`.
- `Pipeline.render_plan_payload` : export JSON debug.
- `Pipeline.render_static_html` : HTML standalone.
- `Pipeline.responsive_manifest` : manifest responsive depuis plusieurs docs.

Debug typique :

- Utile pour tests unitaires simples sans passer par toute la CLI.

## Source Figma Et Normalisation

### `src/figma2hugo/pipeline/fetcher.py`

- `FigmaPipelineTarget` : file key, node id, URL source.
- `parse_figma_pipeline_url` : parse URL Figma et normalise `node-id`.
- `fetch_raw_node_from_figma` : fetch haut niveau d'un node Figma.
- `FigmaPipelineRawClient.fetch_node` : appelle REST Figma nodes/images.
- `FigmaPipelineRawClient.get_node_render_urls` : recupere URLs PNG pour assets et
  references visuelles Figma.
- `resolve_figma_pipeline_token` : lit token local/env pour fetch raw et references.
- `_token_from_env` : lit `FIGMA_ACCESS_TOKEN` / `FIGMA_TOKEN`.
- `_normalize_node_id` : convertit `1-2` en `1:2`.
- `_retry_delay` : backoff si rate-limit.
- `_with_image_fill_urls` : injecte URLs d'images de fills.
- `_image_fill_node_ids_without_url` / `_has_image_fill` : detectent assets a
  recuperer.
- `_with_node_render_urls` : injecte URLs de rendu node.
- `_chunks` : batching API.

Debug typique :

- Si une image est absente des raw, regarder `_with_image_fill_urls`.
- Si un node-id ne marche pas, regarder `parse_figma_pipeline_url`.

### `src/figma2hugo/pipeline/figma_references.py`

- `build_figma_reference_plan` : cree le plan des PNG Figma a comparer depuis
  les groupes Hugo pipeline, les raw payloads et les targets Figma.
- `prepare_figma_reference_images` : exporte les PNG Figma dans le dossier de
  smoke quand aucune baseline projet n'est disponible.
- `_active_plan_for_viewport` : reproduit le choix de variante responsive du
  CSS pipeline pour associer un viewport a la bonne frame Figma.
- `_write_viewport_reference` : redimensionne ou padde l'export Figma pour
  obtenir un PNG comparable au screenshot Hugo du viewport.

Debug typique :

- Si `comparisonKind=figma-reference` mais que tout reste `capture-only`,
  verifier le token Figma et `site-smoke/figma-reference/manifest.json`.
- Si une reference manque, verifier le `nodeId` dans `site/report.json` ->
  `figmaReference.items`.

### `src/figma2hugo/pipeline/models.py`

- `GeometryBox` : geometrie de base avec helpers relatifs.
- `PipelineIssue` : signal diagnostic.
- `RawNode` : representation raw Figma-like.
- `NormalizedNode` : node en coordonnees page.
- `IntermediatePipelineDocument` : page + sections + diagnostics.
- `RenderNodePlan`, `RenderSectionPlan`, `RenderPlan` : contrat de rendu.
- `CoordinateSpace`, `GeometrySource`, `NodeKind`, `IssueSeverity` : enums.

Debug typique :

- Si une donnee disparait entre raw et rendu, verifier le passage
  `RawNode -> NormalizedNode -> RenderNodePlan`.

### `src/figma2hugo/pipeline/normalizer.py`

- `normalize_document` : transforme raw Figma en document pipeline normalise.
- `_section_candidates` : choisit les sections top-level.
- `_promoted_section_children` : remonte une section interne si wrapper vide.
- `_leaf_renderable_section` : trouve une section feuille utile.
- `_is_promotable_wrapper` : determine si un wrapper peut etre ignore.
- `_descendant_sections` : liste sections descendantes.
- `_has_renderable_content` / `_has_direct_renderable_content` : detectent du
  contenu utile.
- `_has_visual_style` : detecte fills visibles.
- `_normalize_node` : normalise recursivement bounds, kind, children.
- `_node_bounds` : source de bounds avec fallback render bounds.
- `_geometry_source` : indique bounding box/render/missing.
- `_infer_kind` : classe TEXT/ASSET/SECTION/CONTAINER.
- `_is_semantic_section_name` : reconnait `section-*` et `region-*`.
- `_safe_payload` : retire `children` du payload stocke.

Debug typique :

- Si `region-*` ou `section-*` n'est pas section, regarder `_infer_kind`.
- Si la page devient une seule section, regarder `no-section-candidates`.

### `src/figma2hugo/pipeline/geometry.py`

- `snap_declared_board_width` : snap des largeurs supportees.
- `snap_page_horizontal_extent` : calcule extent horizontal de page.
- `snap_section_horizontal_box` : aligne une section sur la largeur page.

### `src/figma2hugo/pipeline/generator/css_geometry.py`

- `compute_page_geometry` : derive geometrie CSS de page.
- `compute_section_geometry` : derive geometrie CSS d'une section.

Debug typique :

- Si une section depasse horizontalement ou se decale, regarder ces helpers et
  les diagnostics `section-outside-page-*`.

## Render Plan, Semantique Et Diagnostics

### `src/figma2hugo/pipeline/render_plan.py`

- `build_render_plan` : document normalise -> plan de rendu.
- `_section_plan` : section normalisee -> section render.
- `_node_plan_or_none` : node normalise -> node render ou suppression.
- `_is_renderable` : filtre les nodes sans rendu.
- `_component_for` : deduit composant (`text`, `image`, `form`, `field`,
  `select`, `textarea`, `submit`, etc.).
- `_component_attributes` : attributs HTML/data par composant.
- `_component_render_style` : style specifique au composant.
- `_descendant_text_style_for_label` : style texte pour controles semantiques.
- `_collapse_duplicate_component_wrapper` : retire wrappers redondants.
- `_fit_node_tree_to_parent` : ajuste arbre dans bounds parent.
- `_snap_text_bounds_to_parent` / `_clamp_text_bounds_to_parent` : evite les
  overhangs texte.
- `_looks_like_field` / `_looks_like_select` / `_looks_like_textarea` /
  `_looks_like_submit` : detection generique des controles.
- `_descendant_text` / `_descendant_texts` : recupere texte enfant.
- `_best_label`, `_field_name`, `_input_type`, `_human_label` : labels et noms
  de controles.
- `_section_layout_mode` : layout section.
- `_layer_for` : couche `content`, `decorative`, etc.
- `_text_value` : contenu visible.
- `_asset_url` : URL asset.
- `_render_style` : CSS depuis Figma.
- `_effective_text_style_source` / `_copy_text_style` : styles typo, dont
  overrides Figma.
- `_solid_fill_color` / `_rgba_color` : couleurs CSS.
- `_css_px`, `_float`, `_float_or_none` : conversions.

Debug typique :

- Si un formulaire ne devient pas semantique, regarder `_component_for` et les
  `_looks_like_*`.
- Si la typographie est fausse, regarder `_effective_text_style_source`.

### `src/figma2hugo/pipeline/semantic_adjustments.py`

- `apply_semantic_adjustments` : applique les ajustements bornes et retourne
  plan + issues.
- `_adjust_section` : ajuste une section et deplace les suivantes si besoin.
- `_adjust_node` : dispatch recursif par type de node.
- `_adjust_text_node` : hauteur intrinsique de texte.
- `_adjust_accordion_node` : compacte les panels fermes.
- `_adjust_form_node` : agrandit/repositionne formulaires mobiles trop petits.
- `_adjust_narrow_footer_text` : lisibilite footer legal mobile.
- `_looks_like_footer_legal_text` : detection contenu legal, pas nom seul.
- `_repair_mojibake` : repare variantes mojibake du copyright.
- `_contain_narrow_decorative_overflow` : borne les decors mobiles.
- `_stretch_direct_backgrounds` : etire fonds directs apres expansion.
- `_shift_bottom_anchored_section_nodes` : garde les elements ancres en bas.
- `_form_readability_scale` : ratio d'agrandissement controles.
- `_semantic_controls` : controles utiles dans un formulaire.
- `_horizontal_form_placement` : placement par intervalle libre ou centrage.
- `_push_overlapping_text_siblings` : pousse les textes qui se chevauchent.
- `_text_intrinsic_height` : hauteur theorique de texte.
- `_scale_node_tree` / `_shift_node_tree` : transforms geometriques.
- `_walk_nodes` : parcours recursif.

Debug typique :

- Si le rendu change mais que Figma n'a pas change, chercher les codes
  `*-expanded`, `*-shifted`, `accordion-closed-panel-space`.
- Si une logique semble trop specifique, verifier qu'elle depend d'un type
  semantique ou de geometrie, pas d'un nom de page.

### `src/figma2hugo/pipeline/diagnostics.py`

- `analyze_render_plan` : entree principale diagnostics.
- `_section_bounds_issues` : sections hors page.
- `_vertical_gap_issues` : grands gaps entre sections.
- `_section_overlap_issues` : sections qui se chevauchent.
- `_section_content_issues` : contenu hors section/clippe.
- `_overlap_issues` : collision de nodes.
- `_diagnostic_children` : ignore certains enfants non visibles, ex panels
  accordion fermes.
- `_collision_bounds` : bounds utilises pour overlap.
- `_estimated_text_height` : estimation de hauteur texte.
- `_node_horizontal_tolerance` / `_node_vertical_tolerance` : tolerances.
- `_section_role` : role de section pour tri.
- `_section_gap_threshold` : seuil gap selon page.

Debug typique :

- Si `diagnostics.issueCount` est non-zero, ouvrir `diagnostics.json`, puis
  suivre le code issue vers cette file.

## Responsive Et Contrats

### `src/figma2hugo/pipeline/responsive.py`

- `ResponsiveDecision` : enum de decisions responsive.
- `ResponsiveIssue` : signal responsive.
- `ResponsiveNodeFamily` : famille d'un node sur plusieurs widths.
- `ResponsiveManifest` : manifest global d'une famille de pages.
- `build_responsive_manifest` : compare les variantes responsive.
- `responsive_variant_identity` : extrait width et famille.
- `_node_key` : identite stable d'un node.
- `_content_signature` : signature contenu/structure.
- `_canonical_node_slug` : aliases de noms connus.
- `_is_metadata_node` : ignore metadata non contenu.
- `_normalized_content_text` : normalise whitespace/retours.
- `_content_difference_kind` : type de difference.
- `_responsive_contract_fields` : champs de contrat attaches aux issues.
- `_responsive_node_role` : role metier approximatif.
- `_responsive_contract_risk` : risque de contrat.
- `_has_responsive_content` : node pertinent pour comparaison.

Debug typique :

- Si un signal `content-conflict` semble faux, comparer `_content_signature`
  et `_normalized_content_text`.
- Si un bloc manque sur mobile, regarder `breakpoint-only` et
  `stable-breakpoint-presence`.

### `src/figma2hugo/pipeline/responsive_identity.py`

- `unique_breakpoint_render_name` : genere un nom stable avec suffixe width sans
  accumuler les anciens suffixes.

### `src/figma2hugo/pipeline/review_contract.py`

- `load_responsive_review_contract` : lit un JSON de contrat.
- `normalize_responsive_review_contract` : valide et normalise declarations.
- `find_responsive_review_contract` : matche une issue responsive.
- `responsive_review_contract_summary` : resume matched/unused/invalid.
- `_contract_matches` : matching strict des champs.
- `_contract_fingerprint` : id par defaut.
- `_normalize_contract_value` : normalise scalaires/listes/ints.
- `_public_declaration` : version courte pour rapport.

Debug typique :

- Si `unusedCount > 0`, la declaration ne matche plus les signaux courants.
- Si `invalidCount > 0`, verifier champs requis et `decision`.

### `src/figma2hugo/pipeline/review_baselines.py`

- `ResolvedProjectReviewBaseline` : resultat de resolution projet.
- `resolve_project_review_baseline` : trouve le contrat courant par
  `sourceIdentity.projectId`.
- `promote_project_review_baseline` : cree un snapshot depuis `report.json`.
- `_baseline_candidates` : chemins acceptes.
- `_baseline_compatible` : verifie project identity.
- `_actionable_review_items` : extrait les signaux a promouvoir/verifier.
- `_responsive_contracts_from_items` : transforme actionables responsive en
  `responsiveContracts`.
- `_responsive_contract_from_item` : cree une declaration stricte.
- `_contract_decision` / `_contract_rationale` / `_contract_id` : metadata
  de contrat.
- `_approved_actionable_reviews` : approvals non-responsive optionnels.

Debug typique :

- Si `--responsive-contract-root` ne fait rien, verifier
  `review.projectReviewBaseline`.
- Si le mauvais projet est pris, verifier `sourceIdentity.projectId`.

## Baselines Visuelles Et Smoke

### `src/figma2hugo/pipeline/visual_baselines.py`

- `build_source_identity` : construit `projectId`, `projectHash`,
  `sourceHash`.
- `load_site_source_identity` : lit `site/report.json`.
- `resolve_visual_baseline` : decide off/capture/compare/auto.
- `visual_baseline_manifest` : manifest de capture.
- `promote_visual_baseline` : copie screenshots dans un snapshot projet.
- `_normalize_mode` : mode baseline effectif.
- `_baseline_dir_compatible` : compatibilite avec source identity.
- `_resolve_project_baseline` : snapshot courant depuis index.
- `_copy_screenshots` : copie PNG et dimensions.
- `_report_source_identity` : identity depuis smoke report.
- `_hash_json` : hash stable JSON.

Debug typique :

- Si `auto` capture au lieu de comparer, regarder l'index projet et
  `visualReview.reason`.

### `src/figma2hugo/pipeline/visual_smoke.py`

- `parse_widths` : parse `--widths`.
- `run_pipeline_visual_smoke` : build Hugo, sert le site, capture, compare a la
  baseline projet ou a la reference Figma, ecrit reports.
- `_load_page_slugs` : trouve les routes a tester.
- `_build_hugo_site` : lance Hugo si pas de `--public-dir`.
- `_viewport_for_width` : taille viewport.
- `_visual_review_record` : compare screenshot/baseline et produit status.
- `_pixel_diff_ratio` : ratio pixels differents avec tolerance.
- `_render_review_html` : page review humaine.
- `_render_review_card` / `_render_review_figure` : cartes de diff.
- `_write_contact_sheet` : planche de controle.
- `_visual_status` / `_status_color` : rendu de status.
- `_served_directory` : serveur local temporaire.
- `_image_mime_type` : mime pour images.

Debug typique :

- Toujours ouvrir `site-smoke/review.html` avant de conclure.
- Ordre de comparaison : baseline projet, reference Figma, capture seule.
- Si `height-delta-review`, comparer hauteur baseline vs hauteur nouvelle.

## Rendu Hugo Et Renderers

### `src/figma2hugo/pipeline/hugo_renderer.py`

- `PipelineHugoPage` / `PipelineHugoRenderGroup` : payloads de pages/groupes.
- `write_pipeline_hugo_site` : ecrit un site Hugo depuis plans simples.
- `write_pipeline_hugo_site_groups` : ecrit un site Hugo avec familles responsive.
- `_write_page` : ecrit content/data/css pour une page.
- `_write_responsive_page` : ecrit une page responsive multi-variants.
- `_ensure_hugo_dirs` : cree dossiers Hugo.
- `_clean_pipeline_managed_outputs` : nettoie sorties pipeline gerees.
- `_remove_previous_managed_files` : supprime anciens fichiers listes dans
  manifest.
- `_write_hugo_scaffold` : templates Hugo pipeline.
- `_write_managed_manifest` : `.figma2hugo-pipeline/managed-files.json`.
- `_assert_pipeline_scaffold_writable` : protege fichiers non geres.
- `_localize_group_assets` : localise assets de tous les groupes.
- `_localize_asset_sources` / `_localize_single_asset` : copie/download assets.
- `_copy_cached_remote_asset` / `_store_remote_asset_cache` : cache assets.
- `_localize_plan_assets` / `_localize_node_assets` : remplace URLs assets dans
  le plan.
- `_responsive_css` / `_base_responsive_css` : CSS responsive Hugo.
- `_front_matter` : front matter markdown.

Debug typique :

- Si un fichier utilisateur disparait, verifier le manifest managed-files.
- Si une image ne charge pas, verifier `_localize_single_asset` et
  `static/pipeline-assets`.

### `src/figma2hugo/pipeline/site_renderer.py`

- `write_pipeline_static_site` : preview static debug.
- `_write_responsive_page` : page responsive static.
- `_render_index` : index de preview.
- `_render_responsive_document` : HTML responsive static.
- `_render_responsive_css` / `_base_responsive_css` : CSS responsive static.

Debug typique :

- Utile pour isoler un probleme de rendu avant Hugo.

### `src/figma2hugo/pipeline/html_renderer.py`

- `render_static_document` : document HTML standalone.
- `render_static_body` : body HTML.
- `render_static_css` : CSS standalone.
- `_render_section` : HTML section.
- `_render_node` / `_render_child_node` / `_render_node_at` : nodes HTML.
- `_node_body` : contenu par component.
- `_base_node_attrs` : attrs communs.
- `_form_attrs` / `_link_attrs` : attrs specifiques.
- `_box_style` : style position/taille.
- `_content_bottom` : hauteur page.

Debug typique :

- Si Hugo ajoute une complexite, comparer avec le HTML standalone.

### `src/figma2hugo/pipeline/export.py`

- `render_plan_to_dict` : serialise un plan pour debug/tests.
- `responsive_manifest_to_dict` : serialise un manifest responsive.
- `_section_to_dict` / `_node_to_dict` : sections/nodes.
- `_responsive_issue_to_dict` : issues responsive.

## Release Gate

### `scripts/release_gate.py`

- `GateStep` : resultat d'une commande du gate.
- `run_release_gate` : orchestre build, smoke, checks.
- `_parse_args` : options CLI du gate.
- `_collect_raw_files` : collecte `--raw` et `--raw-dir`.
- `_validate_inputs` : refuse inputs contradictoires.
- `_build_command` : construit commande build pipeline.
- `_visual_smoke_command` : construit commande smoke.
- `_run_command` : execute subprocess avec `PYTHONPATH=src`.
- `_validate_reports` : lit site/smoke/baselines et produit checks.
- `_site_report_checks` : verifie pipeline, pages, diagnostics, responsive,
  review.
- `_review_summary_checks` : bloque `blocking`, `P0`, `P1`, stale contracts.
- `_review_baseline_checks` : exige que les actionables soient approuves.
- `_smoke_report_checks` : smoke issue/error/warn et presence screenshots.
- `_visual_baseline_checks` : compare stricte, status `pass` uniquement.
- `_resolve_project_review_baseline` : resolution projet pour review/contract.
- `_project_review_baseline_exists_check` : check existence/compatibilite.
- `_check` : format commun de check.

Debug typique :

- La sortie JSON du gate contient tout dans `checks[]`. Chercher le premier
  `ok=false`, puis aller au fichier indique par `path`.

## Tests A Lancer Selon Le Symptom

```powershell
# CLI, UI, baselines, gate
$tmp=(Resolve-Path .figma2hugo-scratch).Path + '\pytest-tmp'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$env:TMP=$tmp; $env:TEMP=$tmp; $env:PYTHONPATH='src'
pytest -q tests\test_cli.py tests\test_gui.py tests\test_release_gate.py --basetemp .figma2hugo-scratch\pytest-basetemp

# Pipeline complet
pytest -q tests\test_pipeline.py --basetemp .figma2hugo-scratch\pytest-basetemp

# Qualite code
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m mypy src\figma2hugo
```

## Commandes De Reproduction Utiles

```powershell
# Build live avec refresh Figma
$env:PYTHONPATH='src'
python -m figma2hugo.cli build-site site --page-file pages.txt --refresh-cache

# Smoke auto projet
python -m figma2hugo.cli visual-smoke site --out site-smoke --baseline-mode auto --baseline-root baselines\visual\pipeline\projects

# Promotion visuelle
python -m figma2hugo.cli promote-visual-baseline site-smoke --baseline-root baselines\visual\pipeline\projects --label approved

# Promotion review/contrat
python -m figma2hugo.cli promote-review-baseline site --baseline-root baselines\review\pipeline\projects --label approved

# Gate strict projet
python scripts\release_gate.py .figma2hugo-scratch\release-project --page-file pages.txt --smoke-out .figma2hugo-scratch\release-project-smoke --widths 1920,1440,1280,1024,834,402 --screenshot-widths 1920,1440,1280,1024,834,402 --baseline-mode compare --baseline-root baselines\visual\pipeline\projects --review-baseline-root baselines\review\pipeline\projects --responsive-contract-root baselines\review\pipeline\projects --diff-review-threshold 0.002 --diff-fail-threshold 0.01
```

## Regles De Debug

- Ne pas corriger un symptome dans le renderer si le render plan est deja faux.
- Ne pas promouvoir une baseline pour masquer une regression.
- Ne pas ajouter de logique par nom de page. Preferer type semantique,
  geometrie, role ou contrat explicite.
- Garder `pipeline` autonome : ne pas importer de workflow ou runtime de
  reparation historique.
- Garder les nouveaux ajustements bornes, reportes et testes par fixture.



