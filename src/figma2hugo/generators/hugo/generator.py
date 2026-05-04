from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
from typing import Any

from .._responsive import detect_responsive_variant, merge_responsive_family
from .._shared import (
    CanonicalModelBuilder,
    GenerationArtifacts,
    copy_assets,
    ensure_directory,
    ensure_text,
    locate_templates_root,
    read_template_text,
    slugify,
    write_json_file,
    write_text_file,
)
from ..css import CssGenerator


class HugoGenerator:
    """Génère un site Hugo en conservant un rendu très piloté par Figma.

    La logique est organisée autour de deux idées :
    - produire un scaffold Hugo stable et personnalisable ;
    - protéger les personnalisations humaines contre les régénérations.
    """

    _MANIFEST_RELATIVE_PATH = Path(".figma2hugo") / "managed-hugo-files.json"
    _GENERIC_CONTAINER_ROLES = {"", "container", "group", "frame", "node", "wrapper", "div"}
    _COMPONENT_TEMPLATE_BY_ROLE = {
        "accordion": "accordion",
        "accordion-item": "accordion-item",
        "carousel": "carousel",
        "field": "field",
        "link-grid": "link-grid",
        "link-card": "link-card",
        "card": "card",
    }

    def __init__(self) -> None:
        self._builder = CanonicalModelBuilder(mode="hugo")
        self._css_generator = CssGenerator(include_component_presets=False)
        self._force_managed_overwrite = os.getenv("FIGMA2HUGO_FORCE_MANAGED_OVERWRITE", "0") == "1"

    def generate(self, model: Any, output_dir: str | Path, report: dict[str, Any] | None = None) -> GenerationArtifacts:
        output_path = Path(output_dir)
        managed_hashes, written_files = self._prepare_output_directory(output_path)
        page_data = self._builder.build(model)
        self._annotate_component_partials(page_data, output_path)
        written_files.extend(self._write_single_page_bundle(output_path, page_data))
        if report is not None:
            written_files.append(write_json_file(output_path / "report.json", report))
        if page_data["assets"]:
            ensure_directory(output_path / "static" / "images")
        written_files.extend(self._write_managed_manifest(output_path, managed_hashes))
        return GenerationArtifacts(output_dir=output_path, written_files=tuple(written_files), page_data=page_data)

    def generate_many(
        self,
        models: list[Any],
        output_dir: str | Path,
        report: dict[str, Any] | None = None,
    ) -> GenerationArtifacts:
        output_path = Path(output_dir)
        managed_hashes, written_files = self._prepare_output_directory(output_path)

        built_pages = [self._builder.build(model) for model in models]
        merged_pages = self._merge_responsive_pages(built_pages)

        site_pages: list[dict[str, Any]] = []
        used_slugs: set[str] = set()
        scoped_pages: list[dict[str, Any]] = []

        for index, page_data in enumerate(merged_pages):
            page_slug = self._unique_slug(str(page_data["page"]["slug"]), used_slugs)
            scoped_page = self._scope_page_data(page_data, page_slug)
            stylesheet_path = f"css/pages/{page_slug}.css"
            self._annotate_component_partials(scoped_page, output_path)
            scoped_pages.append(scoped_page)
            written_files.extend(
                self._write_multi_page_bundle(
                    output_path,
                    scoped_page,
                    page_slug=page_slug,
                    weight=index + 1,
                )
            )
            site_pages.append(
                {
                    "title": scoped_page["page"]["title"],
                    "slug": page_slug,
                    "page_key": page_slug,
                    "path": f"/{page_slug}/",
                    "output_path": f"{page_slug}/index.html",
                    "stylesheet": stylesheet_path,
                    "weight": index + 1,
                }
            )

        written_files.append(
            write_text_file(
                output_path / "content" / "_index.md",
                self._home_front_matter(title="Pages"),
            )
        )
        written_files.append(write_json_file(output_path / "data" / "site.json", {"pages": site_pages}))
        if report is not None:
            written_files.append(write_json_file(output_path / "report.json", report))
        if any(page_data["assets"] for page_data in scoped_pages):
            ensure_directory(output_path / "static" / "images")
        written_files.extend(self._write_managed_manifest(output_path, managed_hashes))
        return GenerationArtifacts(
            output_dir=output_path,
            written_files=tuple(written_files),
            page_data={"pages": site_pages},
        )

    def _merge_responsive_pages(self, page_datas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: list[tuple[str, list[dict[str, Any]], str | None]] = []
        grouped_index: dict[str, int] = {}

        for page_data in page_datas:
            detected = detect_responsive_variant(page_data)
            if detected is None:
                group_key = f"single::{len(grouped)}"
                grouped_index[group_key] = len(grouped)
                grouped.append((group_key, [page_data], None))
                continue

            family_slug, _ = detected
            group_key = f"responsive::{family_slug}"
            if group_key not in grouped_index:
                grouped_index[group_key] = len(grouped)
                grouped.append((group_key, [page_data], family_slug))
                continue
            grouped[grouped_index[group_key]][1].append(page_data)

        merged_pages: list[dict[str, Any]] = []
        for _, pages, family_slug in grouped:
            if family_slug and len(pages) > 1:
                merged_pages.append(merge_responsive_family(pages))
            else:
                merged_pages.extend(pages)
        return merged_pages

    def _prepare_output_directory(self, output_path: Path) -> tuple[dict[str, str], list[Path]]:
        ensure_directory(output_path)
        managed_hashes = self._load_managed_hashes(output_path)
        written_files = self._sync_hugo_scaffold(output_path, managed_hashes)
        written_files.extend(self._sync_shared_runtime(output_path, managed_hashes))
        return managed_hashes, written_files

    def _sync_shared_runtime(self, output_path: Path, managed_hashes: dict[str, str]) -> list[Path]:
        return self._sync_managed_text(
            output_path,
            Path("assets") / "js" / "accordion.js",
            self._accordion_script(),
            managed_hashes,
        )

    def _write_single_page_bundle(self, output_path: Path, page_data: dict[str, Any]) -> list[Path]:
        return [
            write_text_file(
                output_path / "content" / "_index.md",
                self._page_front_matter(
                    title=page_data["page"]["title"],
                    page_key="page",
                    stylesheet="css/main.css",
                ),
            ),
            write_text_file(output_path / "assets" / "css" / "main.css", self._css_generator.generate(page_data)),
            write_json_file(output_path / "data" / "page.json", page_data),
            *copy_assets(page_data, output_path, mode="hugo"),
        ]

    def _write_multi_page_bundle(
        self,
        output_path: Path,
        page_data: dict[str, Any],
        *,
        page_slug: str,
        weight: int,
    ) -> list[Path]:
        stylesheet_path = f"css/pages/{page_slug}.css"
        return [
            write_text_file(
                output_path / "content" / f"{page_slug}.md",
                self._page_front_matter(
                    title=page_data["page"]["title"],
                    page_key=page_slug,
                    stylesheet=stylesheet_path,
                    slug=page_slug,
                    weight=weight,
                ),
            ),
            write_text_file(
                output_path / "assets" / stylesheet_path,
                self._css_generator.generate(page_data),
            ),
            write_json_file(output_path / "data" / "pages" / f"{page_slug}.json", page_data),
            *copy_assets(page_data, output_path, mode="hugo"),
        ]

    def _page_front_matter(
        self,
        *,
        title: Any,
        page_key: str,
        stylesheet: str,
        slug: str | None = None,
        weight: int | None = None,
    ) -> str:
        lines = ["---", f'title: "{self._escape_front_matter_string(title)}"']
        if slug:
            lines.append(f'slug: "{self._escape_front_matter_string(slug)}"')
        if weight is not None:
            lines.append(f"weight: {int(weight)}")
        lines.append(f'page_key: "{self._escape_front_matter_string(page_key)}"')
        lines.append(f'stylesheet: "{self._escape_front_matter_string(stylesheet)}"')
        lines.append("---")
        return "\n".join(lines) + "\n"

    def _home_front_matter(self, *, title: Any) -> str:
        return "---\n" f'title: "{self._escape_front_matter_string(title)}"\n' "---\n"

    def _escape_front_matter_string(self, value: Any) -> str:
        return str(value).replace("\\", "\\\\").replace('"', '\\"')

    def _unique_slug(self, slug: str, used_slugs: set[str]) -> str:
        candidate = slug or "page"
        if candidate not in used_slugs:
            used_slugs.add(candidate)
            return candidate
        suffix = 2
        while f"{candidate}-{suffix}" in used_slugs:
            suffix += 1
        unique = f"{candidate}-{suffix}"
        used_slugs.add(unique)
        return unique

    def _scope_page_data(self, page_data: dict[str, Any], page_slug: str) -> dict[str, Any]:
        """Isole les assets d'une page multi-pages pour éviter les collisions."""

        scoped_page = deepcopy(page_data)
        scoped_page["page"]["slug"] = page_slug

        asset_updates = self._scope_assets_for_page(scoped_page, page_slug)

        responsive = scoped_page.get("responsive", {}) or {}
        for variant in responsive.get("variants", []):
            variant_page = variant.get("page", {}) or {}
            self._scope_assets_for_page(variant_page, page_slug, asset_updates=asset_updates)

        return scoped_page

    def _scope_assets_for_page(
        self,
        page_data: dict[str, Any],
        page_slug: str,
        *,
        asset_updates: dict[str, tuple[str, str, str]] | None = None,
    ) -> dict[str, tuple[str, str, str]]:
        updates: dict[str, tuple[str, str, str]] = dict(asset_updates or {})
        for asset in page_data.get("assets", []):
            asset_id = str(asset.get("id") or asset.get("node_id") or "")
            local_path = str(asset.get("local_path") or "").strip()
            public_path = str(asset.get("public_path") or "").strip()
            css_public_path = str(asset.get("css_public_path") or "").strip()
            if asset_id and asset_id in updates:
                scoped_relative_path, scoped_public_path, scoped_css_public_path = updates[asset_id]
            else:
                if not local_path and not public_path and not css_public_path:
                    continue
                relative_path = local_path.lstrip("/")
                if relative_path.startswith("images/"):
                    relative_path = relative_path[len("images/") :]
                if relative_path:
                    scoped_relative_path = f"images/{page_slug}/{relative_path}"
                    scoped_public_path = scoped_relative_path
                    scoped_css_public_path = f"/{scoped_relative_path}"
                else:
                    scoped_relative_path = local_path
                    scoped_public_path = public_path
                    scoped_css_public_path = css_public_path
                if asset_id:
                    updates[asset_id] = (scoped_relative_path, scoped_public_path, scoped_css_public_path)

            asset["local_path"] = scoped_relative_path
            asset["public_path"] = scoped_public_path
            asset["css_public_path"] = scoped_css_public_path

        for section in page_data.get("sections", []):
            self._scope_section_assets(section.get("children", []), updates)
        return updates

    def _scope_section_assets(
        self,
        nodes: list[dict[str, Any]],
        asset_updates: dict[str, tuple[str, str, str]],
    ) -> None:
        for node in nodes:
            if node.get("kind") == "asset":
                asset = node.get("asset", {})
                asset_id = str(asset.get("id") or asset.get("node_id") or "")
                if asset_id in asset_updates:
                    local_path, public_path, css_public_path = asset_updates[asset_id]
                    asset["local_path"] = local_path
                    asset["public_path"] = public_path
                    asset["css_public_path"] = css_public_path
            self._scope_section_assets(node.get("children", []), asset_updates)

    def _accordion_script(self) -> str:
        return read_template_text("shared", "accordion.js")

    def _sync_hugo_scaffold(self, output_path: Path, managed_hashes: dict[str, str]) -> list[Path]:
        templates_root = locate_templates_root() / "hugo"
        written_files: list[Path] = []
        for source_path in sorted(templates_root.rglob("*")):
            if source_path.is_dir():
                continue
            relative_path = source_path.relative_to(templates_root)
            written_files.extend(
                self._sync_managed_text(
                    output_path,
                    relative_path,
                    source_path.read_text(encoding="utf-8"),
                    managed_hashes,
                )
            )
        return written_files

    def _annotate_component_partials(
        self,
        page_data: dict[str, Any],
        output_path: Path,
    ) -> None:
        # Le slug de page sert d'espace de noms pour les overrides éventuels.
        page = page_data.get("page", {}) or {}
        page_slug = slugify(page.get("slug") or page.get("name") or "page", "page")

        for section in page_data.get("sections", []):
            for child in section.get("children", []):
                self._annotate_component_node(
                    child,
                    page_slug=page_slug,
                    output_path=output_path,
                )

    def _annotate_component_node(
        self,
        node: dict[str, Any],
        *,
        page_slug: str,
        output_path: Path,
    ) -> None:
        if node.get("kind") != "container":
            return

        children = list(node.get("children", []))
        template_name = self._component_template_name(node)
        if template_name:
            component_slug = self._component_slug(node)
            custom_relative_path = self._resolve_custom_component_partial(
                output_path,
                page_slug=page_slug,
                component_slug=component_slug,
                template_name=template_name,
            )
            if custom_relative_path is not None:
                node["partial_template"] = custom_relative_path.as_posix()
            else:
                node["partial_template"] = (Path("components") / f"{template_name}.html").as_posix()

        for child in children:
            self._annotate_component_node(
                child,
                page_slug=page_slug,
                output_path=output_path,
            )

    def _component_template_name(self, node: dict[str, Any]) -> str:
        if node.get("kind") != "container":
            return ""
        if not node.get("children"):
            return ""
        role = ensure_text(node.get("role")).strip().lower()
        if role in self._COMPONENT_TEMPLATE_BY_ROLE:
            return self._COMPONENT_TEMPLATE_BY_ROLE[role]
        if role == "section" and self._is_component_like_nested_section(node):
            return "section-block"
        return ""

    def _is_component_like_nested_section(self, node: dict[str, Any]) -> bool:
        attributes = node.get("attributes", {}) or {}
        if str(attributes.get("data-section-block", "")).strip().lower() == "true":
            return True
        layout = node.get("layout", {}) or {}
        return bool(layout.get("use_flow_shell")) and len(node.get("children", [])) >= 2

    def _component_slug(self, node: dict[str, Any]) -> str:
        return slugify(node.get("name") or node.get("dom_id") or node.get("id") or "component", "component")

    def _resolve_custom_component_partial(
        self,
        output_path: Path,
        *,
        page_slug: str,
        component_slug: str,
        template_name: str,
    ) -> Path | None:
        # On préfère d'abord le plus spécifique (page + composant), puis on
        # élargit progressivement vers un override global par type.
        candidates = [
            Path("custom") / "components" / page_slug / f"{component_slug}.html",
            Path("custom") / "components" / page_slug / f"{template_name}.html",
            Path("custom") / "components" / f"{component_slug}.html",
            Path("custom") / "components" / f"{template_name}.html",
        ]
        for candidate in candidates:
            if (output_path / "layouts" / "partials" / candidate).exists():
                return candidate
        return None

    def _load_managed_hashes(self, output_path: Path) -> dict[str, str]:
        manifest_path = output_path / self._MANIFEST_RELATIVE_PATH
        if not manifest_path.exists():
            return {}
        try:
            import json

            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        managed = payload.get("managed", {})
        if not isinstance(managed, dict):
            return {}
        return {str(path): str(file_hash) for path, file_hash in managed.items() if file_hash}

    def _write_managed_manifest(self, output_path: Path, managed_hashes: dict[str, str]) -> list[Path]:
        import json

        manifest_path = output_path / self._MANIFEST_RELATIVE_PATH
        ensure_directory(manifest_path.parent)
        manifest_path.write_text(
            json.dumps({"managed": managed_hashes}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return [manifest_path]

    def _sync_managed_text(
        self,
        output_path: Path,
        relative_path: Path,
        content: str,
        managed_hashes: dict[str, str],
    ) -> list[Path]:
        # Un fichier "géré" n'est réécrit que si :
        # - il n'existe pas encore ;
        # - son contenu correspond exactement à la dernière version générée ;
        # - ou si l'utilisateur force explicitement l'écrasement.
        target_path = output_path / relative_path
        ensure_directory(target_path.parent)
        relative_key = relative_path.as_posix()
        desired_hash = self._hash_text(content)

        if not target_path.exists():
            target_path.write_text(content, encoding="utf-8", newline="\n")
            managed_hashes[relative_key] = desired_hash
            return [target_path]

        current_content = target_path.read_text(encoding="utf-8")
        if current_content == content:
            managed_hashes[relative_key] = desired_hash
            return []

        current_hash = self._hash_text(current_content)
        previous_hash = managed_hashes.get(relative_key)
        if self._force_managed_overwrite or previous_hash == current_hash:
            target_path.write_text(content, encoding="utf-8", newline="\n")
            managed_hashes[relative_key] = desired_hash
            return [target_path]

        return []

    def _hash_text(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
