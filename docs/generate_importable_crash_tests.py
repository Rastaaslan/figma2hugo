from __future__ import annotations

from pathlib import Path
import re
from xml.sax.saxutils import escape


DOCS_DIR = Path(__file__).resolve().parent

BREAKPOINTS = (
    {"width": 1920, "label": "desktop-xl", "content": 1440, "gutter": 96},
    {"width": 1280, "label": "desktop", "content": 1120, "gutter": 80},
    {"width": 1024, "label": "tablet-landscape", "content": 880, "gutter": 72},
    {"width": 768, "label": "tablet", "content": 640, "gutter": 64},
    {"width": 390, "label": "mobile", "content": 326, "gutter": 32},
)


class SvgDoc:
    def __init__(self, width: int, height: int, title: str, desc: str) -> None:
        self.width = width
        self.height = height
        self.lines: list[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
            ),
            f"<title id=\"title\">{escape(title)}</title>",
            f"<desc id=\"desc\">{escape(desc)}</desc>",
            "<defs>",
            "  <linearGradient id=\"heroGrad\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">",
            "    <stop offset=\"0%\" stop-color=\"#16316d\"/>",
            "    <stop offset=\"100%\" stop-color=\"#3d67b1\"/>",
            "  </linearGradient>",
            "  <filter id=\"shadow\" x=\"-10%\" y=\"-10%\" width=\"120%\" height=\"120%\">",
            "    <feDropShadow dx=\"0\" dy=\"12\" stdDeviation=\"18\" flood-color=\"#233047\" flood-opacity=\"0.14\"/>",
            "  </filter>",
            "</defs>",
        ]

    def add(self, line: str) -> None:
        self.lines.append(line)

    def rect(
        self,
        node_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: str,
        stroke: str | None = None,
        stroke_width: float | None = None,
        rx: float | None = None,
        extra: str = "",
    ) -> None:
        attrs = [
            f'id="{escape(node_id)}"',
            f'x="{x:.2f}"',
            f'y="{y:.2f}"',
            f'width="{width:.2f}"',
            f'height="{height:.2f}"',
            f'fill="{fill}"',
        ]
        if stroke:
            attrs.append(f'stroke="{stroke}"')
        if stroke_width is not None:
            attrs.append(f'stroke-width="{stroke_width:.2f}"')
        if rx is not None:
            attrs.append(f'rx="{rx:.2f}"')
        if extra:
            attrs.append(extra)
        self.add(f"  <rect {' '.join(attrs)}/>")

    def polygon(self, node_id: str, points: list[tuple[float, float]], *, fill: str) -> None:
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.add(f'  <polygon id="{escape(node_id)}" points="{pts}" fill="{fill}"/>')

    def text(
        self,
        node_id: str,
        x: float,
        y: float,
        content: str,
        *,
        size: int = 18,
        fill: str = "#17306b",
        weight: int = 400,
        family: str = "'Segoe UI', Arial, sans-serif",
        anchor: str = "start",
        opacity: float | None = None,
    ) -> None:
        attrs = [
            f'id="{escape(node_id)}"',
            f'x="{x:.2f}"',
            f'y="{y:.2f}"',
            f'font-family="{family}"',
            f'font-size="{size}"',
            f'font-weight="{weight}"',
            f'fill="{fill}"',
            f'text-anchor="{anchor}"',
        ]
        if opacity is not None:
            attrs.append(f'opacity="{opacity:.2f}"')
        self.add(f"  <text {' '.join(attrs)}>{escape(content)}</text>")

    def open_group(self, node_id: str) -> None:
        self.add(f'  <g id="{escape(node_id)}">')

    def close_group(self) -> None:
        self.add("  </g>")

    def write(self, path: Path) -> None:
        payload = "\n".join(self.lines + ["</svg>", ""])
        path.write_text(payload, encoding="utf-8")


def _page_metrics(width: int) -> tuple[float, float]:
    if width >= 1280:
        return 0.56, 0.22
    if width >= 768:
        return 0.52, 0.34
    return 1.0, 1.0


def _hero(doc: SvgDoc, x: float, y: float, content_w: float) -> float:
    hero_h = 300 if content_w > 700 else 260
    doc.open_group("section-hero")
    doc.rect("bg-hero", x, y, content_w, hero_h, fill="url(#heroGrad)", rx=28)
    doc.polygon("decor-hero-gauche", [(x + 24, y + 18), (x + 120, y + 18), (x + 72, y + 86)], fill="#d06d63")
    doc.polygon(
        "decor-hero-droite",
        [(x + content_w - 120, y + hero_h - 34), (x + content_w - 24, y + hero_h - 34), (x + content_w - 72, y + hero_h - 102)],
        fill="#6e83b9",
    )
    doc.open_group("hero-content")
    doc.text("titre-h1-hero", x + 36, y + 74, "Crash test canonique", size=34 if content_w > 700 else 28, fill="#fffaf4", weight=700)
    doc.text(
        "texte-hero",
        x + 36,
        y + 118,
        "Page importable dans Figma pour valider le convertisseur, les composants et la robustesse responsive.",
        size=18 if content_w > 700 else 16,
        fill="#fffaf4",
    )
    doc.open_group("button-hero")
    btn_y = y + hero_h - 80
    doc.polygon(
        "bg-button-hero",
        [(x + 36, btn_y), (x + 212, btn_y), (x + 188, btn_y + 46), (x + 12, btn_y + 46)],
        fill="#d06d63",
    )
    doc.text("texte-button-hero", x + 64, btn_y + 30, "Demarrer le crash test", size=18, fill="#fffaf4", weight=700)
    doc.close_group()
    doc.close_group()
    media_w = min(420, content_w * 0.34)
    doc.open_group("hero-media")
    doc.rect("image-hero", x + content_w - media_w - 36, y + 42, media_w, hero_h - 84, fill="#ffffff22", stroke="#ffffff55", stroke_width=2, rx=22)
    doc.text("image-hero-label", x + content_w - media_w, y + 96, "image-hero", family="'Cascadia Code', Consolas, monospace", size=16, fill="#fffaf4")
    doc.close_group()
    doc.close_group()
    return hero_h


def _split_section(doc: SvgDoc, x: float, y: float, content_w: float, stack: bool) -> float:
    section_h = 320 if stack else 260
    doc.open_group("section-prestation")
    doc.rect("section-prestation-shell", x, y, content_w, section_h, fill="#f5eee4", stroke="#dccfbe", stroke_width=2, rx=26)
    doc.open_group("section-block-prestation")
    doc.text("section-prestation-label", x + 24, y + 40, "section-prestation", size=26, weight=700)
    doc.open_group("row-prestation")
    gap = 28
    col_w = content_w if stack else (content_w - gap) / 2
    top = y + 62
    left_h = 118 if stack else 150
    doc.open_group("col-prestation-content")
    doc.rect("col-prestation-content-box", x + 24, top, col_w - 24, left_h, fill="#ffffff", stroke="#dccfbe", stroke_width=1.5, rx=18)
    doc.text("titre-h2-prestation", x + 44, top + 40, "section-block-prestation", family="'Cascadia Code', Consolas, monospace", size=19, weight=700)
    doc.text("texte-prestation", x + 44, top + 72, "Bloc editorial deux colonnes pour valider la structure.", size=16)
    doc.open_group("button-prestation")
    btn_y = top + left_h - 52
    doc.polygon("bg-button-prestation", [(x + 44, btn_y), (x + 192, btn_y), (x + 174, btn_y + 38), (x + 26, btn_y + 38)], fill="#16316d")
    doc.text("texte-button-prestation", x + 64, btn_y + 25, "button-prestation", size=15, fill="#fffaf4", family="'Cascadia Code', Consolas, monospace")
    doc.close_group()
    doc.close_group()
    media_x = x + 24 if stack else x + col_w + gap
    media_y = top + left_h + 20 if stack else top
    media_h = 118 if stack else 150
    doc.open_group("col-prestation-media")
    doc.rect("bg-media-prestation", media_x, media_y, col_w - 24, media_h, fill="#efe5d9", stroke="#dccfbe", stroke_width=1.5, rx=18)
    doc.rect("image-prestation", media_x + 18, media_y + 18, col_w - 60, media_h - 54, fill="#d8e3f5", stroke="#bdcde8", stroke_width=1, rx=14)
    doc.polygon("decor-prestation-1", [(media_x + 24, media_y + 20), (media_x + 52, media_y + 20), (media_x + 38, media_y + 46)], fill="#d06d63")
    doc.polygon(
        "decor-prestation-2",
        [(media_x + col_w - 58, media_y + media_h - 16), (media_x + col_w - 24, media_y + media_h - 16), (media_x + col_w - 40, media_y + media_h - 46)],
        fill="#6e83b9",
    )
    doc.close_group()
    doc.close_group()
    doc.close_group()
    return section_h


def _card(
    doc: SvgDoc,
    group_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    title: str,
    body: str,
    href_id: str,
    href_value: str,
) -> None:
    match = re.search(r"projet-(\d+)", group_id)
    index = match.group(1) if match else group_id.split("-")[-1]
    doc.open_group(group_id)
    doc.rect(f"bg-card-projet-{index}", x, y, width, height, fill="#ffffff", stroke="#dccfbe", stroke_width=1.5, rx=18)
    doc.rect(f"image-card-projet-{index}", x + 16, y + 16, width - 32, height * 0.46, fill="#dce7f7", stroke="#c6d5ee", stroke_width=1, rx=12)
    doc.text(f"link-label-projet-{index}", x + 20, y + height * 0.46 + 44, title, size=18, weight=700)
    doc.text(f"texte-projet-{index}", x + 20, y + height * 0.46 + 74, body, size=15, fill="#41506d")
    doc.text(href_id, x + 20, y + height - 18, href_value, size=12, fill="#7c6d60", family="'Cascadia Code', Consolas, monospace")
    doc.close_group()


def _cards_section(doc: SvgDoc, x: float, y: float, content_w: float, columns: int) -> float:
    rows = 2 if columns == 1 else 1
    outer_h = 580 if columns == 1 else 350
    doc.open_group("section-cas-clients")
    doc.rect("section-cas-clients-shell", x, y, content_w, outer_h, fill="#fffdf9", stroke="#dccfbe", stroke_width=2, rx=26)
    doc.text("titre-h2-cas-clients", x + 24, y + 40, "Cas clients", size=26, weight=700)
    doc.open_group("link-grid-cas-clients")
    gap = 20
    card_w = (content_w - 48 - gap * (columns - 1)) / columns
    card_h = 240
    row1_y = y + 74
    row2_y = row1_y + card_h + gap
    doc.open_group("link-row-1")
    _card(
        doc,
        "href-card-projet-1-external",
        x + 24,
        row1_y,
        card_w,
        card_h,
        title="Projet audit",
        body="Card lien externe avec image, label et href.",
        href_id="href-projet-1",
        href_value="https://example.com/projet-1",
    )
    if columns > 1:
        _card(
            doc,
            "href-card-projet-2",
            x + 24 + card_w + gap,
            row1_y,
            card_w,
            card_h,
            title="Projet expertise",
            body="Card interne pour verifier la grille et le clic.",
            href_id="href-projet-2",
            href_value="https://example.com/projet-2",
        )
        if columns > 2:
            _card(
                doc,
                "href-card-projet-3",
                x + 24 + (card_w + gap) * 2,
                row1_y,
                card_w,
                card_h,
                title="Projet formation",
                body="Troisieme card pour la matrice de liens.",
                href_id="href-projet-3",
                href_value="https://example.com/projet-3",
            )
    doc.close_group()
    if columns == 1:
        doc.open_group("link-row-2")
        _card(
            doc,
            "href-card-projet-2",
            x + 24,
            row2_y,
            card_w,
            card_h,
            title="Projet expertise",
            body="Card interne pour verifier la grille et le clic.",
            href_id="href-projet-2",
            href_value="https://example.com/projet-2",
        )
        _card(
            doc,
            "href-card-projet-3",
            x + 24,
            row2_y + card_h + gap,
            card_w,
            card_h,
            title="Projet formation",
            body="Troisieme card pour la matrice de liens.",
            href_id="href-projet-3",
            href_value="https://example.com/projet-3",
        )
        doc.close_group()
    doc.close_group()
    doc.close_group()
    return outer_h


def _faq_section(doc: SvgDoc, x: float, y: float, width: float, compact: bool) -> float:
    section_h = 320 if not compact else 280
    doc.open_group("section-faq")
    doc.rect("section-faq-shell", x, y, width, section_h, fill="#fbf7f1", stroke="#dccfbe", stroke_width=2, rx=26)
    doc.text("titre-h2-faq", x + 24, y + 40, "FAQ", size=26, weight=700)
    doc.open_group("accordion-single-faq")
    item_y = y + 70
    item_gap = 18
    trigger_h = 46
    panel_h = 74 if not compact else 60
    questions = [
        ("accordion-item-1-open", "accordion-trigger-1", "accordion-panel-1", "texte-question-1", "texte-reponse-1", "Comment valider le build ?", "Le validateur controle le build, les assets, les textes, le responsive et les interactions."),
        ("accordion-item-2-closed", "accordion-trigger-2", "accordion-panel-2", "texte-question-2", "texte-reponse-2", "Comment verifier les cards ?", "Les href-card sont sondees sur desktop et mobile par le validateur."),
        ("accordion-item-3-closed", "accordion-trigger-3", "accordion-panel-3", "texte-question-3", "texte-reponse-3", "Comment verifier le carousel ?", "Les thumbs, le stage et les transitions sont controles si le composant est present."),
    ]
    for index, (item_id, trigger_id, panel_id, q_id, a_id, q, a) in enumerate(questions):
        doc.open_group(item_id)
        doc.open_group(trigger_id)
        doc.rect(f"{trigger_id}-shape", x + 20, item_y, width - 40, trigger_h, fill="#ffffff", stroke="#dccfbe", stroke_width=1.2, rx=12)
        doc.text(q_id, x + 36, item_y + 29, q, size=15 if compact else 16)
        doc.close_group()
        panel_y = item_y + trigger_h + 8
        doc.open_group(panel_id)
        panel_fill = "#f5efe6" if index == 0 else "#f7f2ea"
        doc.rect(f"{panel_id}-shape", x + 20, panel_y, width - 40, panel_h, fill=panel_fill, stroke="#e7dccf", stroke_width=1, rx=12)
        doc.text(a_id, x + 36, panel_y + 28, a, size=14, fill="#425168")
        doc.close_group()
        doc.close_group()
        item_y = panel_y + panel_h + item_gap
    doc.close_group()
    doc.close_group()
    return section_h


def _carousel_section(doc: SvgDoc, x: float, y: float, width: float, compact: bool) -> float:
    section_h = 320 if not compact else 280
    doc.open_group("section-carousel")
    doc.rect("section-carousel-shell", x, y, width, section_h, fill="#f4ede3", stroke="#dccfbe", stroke_width=2, rx=26)
    doc.text("titre-h2-carousel", x + 24, y + 40, "Carousel", size=26, weight=700)
    doc.open_group("carousel-gallery")
    doc.open_group("carousel-stage-gallery")
    stage_y = y + 74
    stage_h = 160 if compact else 172
    doc.open_group("carousel-slide-1-active")
    doc.rect("image-slide-1", x + 24, stage_y, width - 48, stage_h, fill="#d8e3f5", stroke="#c6d5ee", stroke_width=1.2, rx=16)
    doc.text("image-slide-1-label", x + 42, stage_y + 30, "image-slide-1", family="'Cascadia Code', Consolas, monospace", size=15)
    doc.close_group()
    doc.open_group("carousel-slide-2")
    doc.rect("image-slide-2", x + 24, stage_y, width - 48, stage_h, fill="#e4d9cc", stroke="#d5c2ab", stroke_width=1.2, rx=16, extra='opacity="0.45"')
    doc.close_group()
    doc.open_group("carousel-slide-3")
    doc.rect("image-slide-3", x + 24, stage_y, width - 48, stage_h, fill="#dce7f7", stroke="#b6cae9", stroke_width=1.2, rx=16, extra='opacity="0.25"')
    doc.close_group()
    doc.close_group()
    thumbs_y = stage_y + stage_h + 18
    doc.open_group("carousel-thumbs-gallery")
    thumb_gap = 14
    thumb_w = (width - 48 - thumb_gap * 2) / 3
    for i in range(3):
        thumb_id = f"carousel-thumb-{i + 1}"
        doc.open_group(thumb_id)
        doc.rect(f"image-thumb-{i + 1}", x + 24 + i * (thumb_w + thumb_gap), thumbs_y, thumb_w, 38, fill="#ffffff", stroke="#dccfbe", stroke_width=1, rx=10)
        doc.text(f"image-thumb-{i + 1}-label", x + 36 + i * (thumb_w + thumb_gap), thumbs_y + 25, f"image-thumb-{i + 1}", family="'Cascadia Code', Consolas, monospace", size=13)
        doc.close_group()
    doc.close_group()
    doc.close_group()
    doc.close_group()
    return section_h


def _form_field(doc: SvgDoc, group_id: str, x: float, y: float, width: float, label: str, *, required: bool = False) -> None:
    doc.open_group(group_id)
    zone_id = "zone-" + group_id.removeprefix("input-").removesuffix("-required")
    placeholder_id = "placeholder-" + group_id.removeprefix("input-").removesuffix("-required")
    doc.rect(zone_id, x, y, width, 54, fill="#7182b2", rx=12)
    doc.text(placeholder_id, x + 14, y + 33, label, size=15, fill="#edf3ff")
    if required:
        doc.text(f"{group_id}-required-flag", x + width - 18, y + 20, "*", size=16, fill="#ffd8d2", weight=700, anchor="end")
    doc.close_group()


def _contact_section(doc: SvgDoc, x: float, y: float, content_w: float, stack: bool) -> float:
    section_h = 570 if stack else 520
    form_w = content_w - 48 if stack else min(760, content_w * 0.56)
    form_h = 360
    doc.open_group("section-contact")
    doc.rect("section-contact-shell", x, y, content_w, section_h, fill="#122c67", rx=28)
    doc.text("titre-h2-contact", x + 24, y + 42, "Contact", size=28, weight=700, fill="#fffaf4")
    doc.open_group("formulaire-contact-post")
    form_x = x + 24
    form_y = y + 74
    doc.rect("bg-contact-formulaire", form_x, form_y, form_w, form_h, fill="#122c67", stroke="#3f5b97", stroke_width=1.2, rx=18)
    _form_field(doc, "input-nom-prenom-required", form_x, form_y, form_w, "Nom et Prenom", required=True)
    _form_field(doc, "input-societe", form_x, form_y + 68, form_w, "Votre societe")
    doc.open_group("ligne-contact")
    half_gap = 14
    half_w = (form_w - half_gap) / 2
    _form_field(doc, "input-telephone", form_x, form_y + 136, half_w, "Votre telephone")
    _form_field(doc, "input-mail-required", form_x + half_w + half_gap, form_y + 136, half_w, "Votre email", required=True)
    doc.close_group()
    doc.open_group("input-select-demande-required")
    doc.rect("zone-demande", form_x, form_y + 204, form_w, 54, fill="#7182b2", rx=12)
    doc.text("option-choix-demande-selected", form_x + 14, form_y + 237, "choisir|Choisissez le sujet de votre demande", size=15, fill="#edf3ff")
    doc.text("option-demande-audit", form_x + 20, form_y + 280, "audit|Audit", size=12, fill="#d8e3f5", family="'Cascadia Code', Consolas, monospace")
    doc.text("option-demande-expertise", form_x + 140, form_y + 280, "expertise|Expertise", size=12, fill="#d8e3f5", family="'Cascadia Code', Consolas, monospace")
    doc.text("option-demande-formation", form_x + 320, form_y + 280, "formation|Formation", size=12, fill="#d8e3f5", family="'Cascadia Code', Consolas, monospace")
    doc.close_group()
    doc.open_group("input-message-required")
    doc.rect("zone-message", form_x, form_y + 298, form_w, 106, fill="#7182b2", rx=12)
    doc.text("placeholder-message", form_x + 14, form_y + 330, "Votre message", size=15, fill="#edf3ff")
    doc.close_group()
    doc.text("action-contact", form_x, form_y + form_h + 28, "https://example.com/contact", size=12, fill="#d8e3f5", family="'Cascadia Code', Consolas, monospace")
    doc.open_group("button-envoyer")
    btn_y = form_y + form_h + 60
    doc.polygon("bg-button-envoyer", [(form_x + 36, btn_y), (form_x + 204, btn_y), (form_x + 176, btn_y + 48), (form_x + 8, btn_y + 48)], fill="#d06d63")
    doc.text("texte-button-envoyer", form_x + 64, btn_y + 31, "button-envoyer", size=18, fill="#fffaf4", weight=700)
    doc.close_group()
    doc.close_group()

    media_x = form_x if stack else form_x + form_w + 28
    media_y = form_y + form_h + 140 if stack else form_y
    media_w = form_w if stack else content_w - (media_x - x) - 24
    media_h = 220 if stack else 360
    doc.open_group("contact-media")
    doc.rect("image-contact", media_x, media_y, media_w, media_h, fill="#d8e3f5", stroke="#bdd0ea", stroke_width=1.2, rx=18)
    doc.text("image-contact-label", media_x + 20, media_y + 34, "image-contact", family="'Cascadia Code', Consolas, monospace", size=16)
    doc.close_group()
    doc.close_group()
    return section_h if not stack else media_y + media_h - y + 24


def _footer(doc: SvgDoc, x: float, y: float, content_w: float) -> float:
    footer_h = 170
    doc.open_group("footer-site")
    doc.rect("footer-site-shell", x, y, content_w, footer_h, fill="#f5eee4", stroke="#dccfbe", stroke_width=2, rx=24)
    doc.open_group("footer-content")
    doc.open_group("footer-brand")
    doc.rect("logo-footer", x + 24, y + 50, 44, 44, fill="#16316d", rx=10)
    doc.text("texte-footer-brand", x + 84, y + 78, "Embedded In Mind", size=18, weight=700)
    doc.close_group()
    doc.open_group("footer-nav")
    doc.open_group("href-card-footer-1")
    doc.text("link-label-footer-1", x + 24, y + 118, "Mentions legales", size=16)
    doc.text("href-footer-1", x + 184, y + 118, "https://example.com/mentions-legales", size=12, fill="#7c6d60", family="'Cascadia Code', Consolas, monospace")
    doc.close_group()
    doc.close_group()
    doc.open_group("footer-legal")
    doc.text("texte-footer-legal", x + content_w - 24, y + 118, "2026 - Crash test figma2hugo", size=15, fill="#7c6d60", anchor="end")
    doc.close_group()
    doc.close_group()
    doc.close_group()
    return footer_h


def build_breakpoint(width: int, label: str, content: int, gutter: int) -> None:
    content_w = float(content)
    side = (width - content_w) / 2
    split_ratio, contact_stack_trigger = _page_metrics(width)
    gap = 28
    split_top = 506
    faq_y = 0  # set later
    contact_y = 0
    footer_y = 0

    hero_h = 300 if content_w > 700 else 260
    split_h = 320 if width < 768 else 260
    cards_h = 580 if width < 768 else 350
    side_by_side = width >= 1024
    faq_h = 320 if side_by_side else 280
    carousel_h = 320 if side_by_side else 280

    if side_by_side:
        content_mid_h = max(faq_h, carousel_h)
        contact_y = 74 + hero_h + gap + split_h + gap + cards_h + gap + content_mid_h + gap
    else:
        contact_y = 74 + hero_h + gap + split_h + gap + cards_h + gap + faq_h + gap + carousel_h + gap

    contact_h = 520 if width >= 1024 else 570
    if width < 768:
        contact_h = 760
    footer_y = contact_y + contact_h + gap
    page_h = int(footer_y + 170 + 74)

    page_name = f"page-crash-test-{width}"
    doc = SvgDoc(width, page_h, f"Crash test importable {width}", f"Page de crash test importable pour largeur {width}.")
    doc.rect("page-bg", 0, 0, width, page_h, fill="#f6f0e7")
    doc.open_group(page_name)
    doc.rect(page_name + "-shell", side, 36, content_w, page_h - 72, fill="#fffdf9", stroke="#dccfbe", stroke_width=2, rx=32, extra='filter="url(#shadow)"')
    doc.text(page_name + "-title", side + 24, 78, f"Crash Test Importable {width}px", size=32, weight=700)
    doc.text(page_name + "-subtitle", side + 24, 110, page_name, size=18, fill="#7c6d60", family="'Cascadia Code', Consolas, monospace")
    doc.text(page_name + "-hint", side + content_w - 24, 110, f"{label} | content {content}px | gutter {gutter}px", size=16, fill="#7c6d60", anchor="end")

    doc.open_group("seo-meta")
    doc.rect("seo-meta-shell", side + 24, 130, content_w - 48, 74, fill="#f8f1e8", stroke="#e7dccf", stroke_width=1.4, rx=16)
    doc.text("seo-title", side + 44, 164, "Crash test figma2hugo", size=18, weight=700)
    doc.text("seo-description", side + 44, 190, "Page canonique importable pour verifier le pipeline, les composants et la robustesse responsive.", size=15, fill="#5c5b66")
    doc.close_group()

    current_y = 228
    hero_h = _hero(doc, side + 24, current_y, content_w - 48)
    current_y += hero_h + gap
    split_h = _split_section(doc, side + 24, current_y, content_w - 48, width < 768)
    current_y += split_h + gap
    cards_h = _cards_section(doc, side + 24, current_y, content_w - 48, 3 if width >= 1280 else 2 if width >= 768 else 1)
    current_y += cards_h + gap
    if width >= 1024:
        half_gap = 20
        half_w = (content_w - 48 - half_gap) / 2
        _faq_section(doc, side + 24, current_y, half_w, False)
        _carousel_section(doc, side + 24 + half_w + half_gap, current_y, half_w, False)
        current_y += max(faq_h, carousel_h) + gap
    else:
        faq_h = _faq_section(doc, side + 24, current_y, content_w - 48, True)
        current_y += faq_h + gap
        carousel_h = _carousel_section(doc, side + 24, current_y, content_w - 48, True)
        current_y += carousel_h + gap

    contact_h = _contact_section(doc, side + 24, current_y, content_w - 48, width < 1024)
    current_y += contact_h + gap
    _footer(doc, side + 24, current_y, content_w - 48)
    doc.close_group()

    out = DOCS_DIR / f"crash-test-importable-{width}.svg"
    doc.write(out)


def main() -> None:
    for breakpoint in BREAKPOINTS:
        build_breakpoint(
            width=breakpoint["width"],
            label=breakpoint["label"],
            content=breakpoint["content"],
            gutter=breakpoint["gutter"],
        )


if __name__ == "__main__":
    main()
