from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape


DOCS_DIR = Path(__file__).resolve().parent

VARIANTS = (
    {"width": 1920, "page_width": 1920, "page_height": 4200, "label": "desktop-xl"},
    {"width": 1280, "page_width": 1280, "page_height": 4500, "label": "desktop"},
    {"width": 768, "page_width": 768, "page_height": 5300, "label": "tablet"},
    {"width": 390, "page_width": 390, "page_height": 6600, "label": "mobile"},
)

COLORS = {
    "page_bg": "#f8f5ef",
    "surface": "#fffdfa",
    "navy": "#11306d",
    "navy_soft": "#6d83b7",
    "salmon": "#d56f63",
    "line": "#ddd1c1",
    "text": "#1f2d45",
    "muted": "#7e6d5f",
    "photo": "#dbe4f3",
}


class Svg:
    def __init__(self, width: int, height: int, title: str) -> None:
        self.width = width
        self.height = height
        self.lines: list[str] = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}">'
            ),
            "<defs>",
            "  <style>",
            "    .sans { font-family: 'Segoe UI', Arial, sans-serif; }",
            "    .mono { font-family: 'Cascadia Code', Consolas, monospace; }",
            "  </style>",
            "</defs>",
            f'<title>{escape(title)}</title>',
        ]

    def add(self, line: str) -> None:
        self.lines.append(line)

    def group_open(self, node_id: str) -> None:
        self.add(f'  <g id="{escape(node_id)}">')

    def group_close(self) -> None:
        self.add("  </g>")

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
        stroke_width: float = 0,
        rx: float = 0,
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
            attrs.append(f'stroke-width="{stroke_width:.2f}"')
        if rx:
            attrs.append(f'rx="{rx:.2f}"')
        self.add(f"    <rect {' '.join(attrs)}/>")

    def polygon(self, node_id: str, points: list[tuple[float, float]], *, fill: str) -> None:
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.add(f'    <polygon id="{escape(node_id)}" points="{pts}" fill="{fill}"/>')

    def text(
        self,
        node_id: str,
        x: float,
        y: float,
        content: str,
        *,
        size: int,
        fill: str,
        weight: int = 400,
        anchor: str = "start",
        family: str = "sans",
    ) -> None:
        self.add(
            "    "
            + f'<text id="{escape(node_id)}" x="{x:.2f}" y="{y:.2f}" '
            + f'class="{family}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">'
            + f"{escape(content)}</text>"
        )

    def write(self, path: Path) -> None:
        path.write_text("\n".join(self.lines + ["</svg>", ""]), encoding="utf-8")


def _is_mobile(width: int) -> bool:
    return width <= 390


def _is_tablet(width: int) -> bool:
    return 391 <= width <= 768


def _content_bounds(page_width: int) -> tuple[float, float]:
    if page_width >= 1920:
        return 120.0, 1680.0
    if page_width >= 1280:
        return 80.0, 1120.0
    if page_width >= 768:
        return 48.0, 672.0
    return 24.0, 342.0


def draw_variant(width: int, page_width: int, page_height: int, label: str) -> Svg:
    svg = Svg(page_width, page_height, f"Responsive crash test {width}")
    margin_x, content_w = _content_bounds(page_width)
    y = 32.0

    svg.rect("page-bg", 0, 0, page_width, page_height, fill=COLORS["page_bg"])
    svg.group_open(f"page-crash-test-{width}")
    svg.rect(f"page-crash-test-{width}-shell", margin_x, y, content_w, page_height - 64, fill=COLORS["surface"], stroke=COLORS["line"], stroke_width=2, rx=28)
    svg.text("page-label", margin_x + 20, y + 28, f"page-crash-test-{width}", size=18, fill=COLORS["muted"], weight=600, family="mono")
    svg.text("page-width-label", margin_x + content_w - 16, y + 28, label, size=16, fill=COLORS["muted"], weight=500, anchor="end", family="mono")
    y += 44

    y = draw_hero(svg, width, margin_x + 24, y + 16, content_w - 48)
    y = draw_accompagnement(svg, width, margin_x + 24, y + 28, content_w - 48)
    y = draw_bandeau_cta(svg, width, margin_x + 24, y + 28, content_w - 48)
    y = draw_embedded(svg, width, margin_x + 24, y + 28, content_w - 48)
    y = draw_valeurs(svg, width, margin_x + 24, y + 28, content_w - 48)
    y = draw_contact(svg, width, margin_x + 24, y + 28, content_w - 48)
    draw_footer(svg, width, margin_x + 24, y + 28, content_w - 48)
    svg.group_close()
    return svg


def draw_hero(svg: Svg, width: int, x: float, y: float, w: float) -> float:
    h = 430 if width >= 1280 else 390 if width >= 768 else 500
    svg.group_open("section-hero")
    svg.rect("bg-hero", x, y, w, h, fill=COLORS["navy"], rx=24)
    svg.text("titre-h1-hero", x + 48, y + 90, "titre-h1-hero", size=42 if width >= 1280 else 34 if width >= 768 else 30, fill="#ffffff", weight=700)
    svg.text("texte-hero", x + 48, y + 142, "texte-hero", size=22 if width >= 1280 else 18 if width >= 768 else 16, fill=COLORS["salmon"], weight=500)
    if _is_mobile(width):
        svg.text("hero-mobile-note", x + 48, y + 176, "hero-mobile-note", size=14, fill="#ffffff", family="mono")
    media_w = w * (0.38 if width >= 768 else 0.62)
    media_h = h * (0.58 if width >= 768 else 0.34)
    media_x = x + w - media_w - 42
    media_y = y + 42
    svg.rect("image-hero", media_x, media_y, media_w, media_h, fill=COLORS["photo"], stroke="#bfd0eb", stroke_width=2, rx=20)
    svg.text("image-hero-label", media_x + 18, media_y + 30, "image-hero", size=16, fill=COLORS["navy"], family="mono")
    svg.polygon("decor-hero-1", [(x + 22, y + h - 92), (x + 96, y + h - 92), (x + 58, y + h - 26)], fill=COLORS["salmon"])
    svg.polygon("decor-hero-2", [(media_x + media_w - 42, media_y - 8), (media_x + media_w + 16, media_y + 12), (media_x + media_w - 14, media_y + 68)], fill=COLORS["navy_soft"])
    if width >= 768:
        svg.polygon("decor-hero-3", [(x + w - 210, y + h - 86), (x + w - 148, y + h - 74), (x + w - 188, y + h - 22)], fill=COLORS["navy_soft"])
    svg.group_close()
    return y + h


def draw_accompagnement(svg: Svg, width: int, x: float, y: float, w: float) -> float:
    stack = width < 768
    h = 520 if stack else 360
    svg.group_open("section-accompagnement")
    svg.text("titre-h2-accompagnement", x + w / 2, y + 54, "titre-h2-accompagnement", size=34 if width >= 1280 else 30 if width >= 768 else 26, fill=COLORS["navy"], weight=700, anchor="middle")
    gap = 28
    card_w = w - 48 if stack else (w - 24 - gap) / 2
    base_y = y + 92
    draw_prestation_card(svg, "card-prestation-1", x + 12, base_y, card_w, 180)
    second_y = base_y + 208 if stack else base_y
    second_x = x + 12 if stack else x + 12 + card_w + gap
    draw_prestation_card(svg, "card-prestation-2", second_x, second_y, card_w, 180)
    btn_y = y + h - 72
    draw_button(svg, "button-accompagnement", x + (w - 290) / 2, btn_y, 290, 48, "Tous nos accompagnements")
    svg.group_close()
    return y + h


def draw_prestation_card(svg: Svg, group_id: str, x: float, y: float, w: float, h: float) -> None:
    svg.group_open(group_id)
    svg.rect(f"{group_id}-shell", x, y, w, h, fill=COLORS["surface"], stroke=COLORS["line"], stroke_width=1.5, rx=16)
    suffix = group_id.split("-")[-1]
    svg.text(f"titre-h3-prestation-{suffix}", x + w / 2, y + 34, f"titre-h3-prestation-{suffix}", size=22, fill=COLORS["navy"], weight=700, anchor="middle")
    svg.text(f"texte-prestation-{suffix}", x + w / 2, y + 78, f"texte-prestation-{suffix}", size=18, fill=COLORS["salmon"], weight=600, anchor="middle")
    svg.text(f"texte-prestation-{suffix}-details", x + 22, y + 122, f"texte-prestation-{suffix}-details", size=14, fill=COLORS["text"], family="mono")
    svg.group_close()


def draw_bandeau_cta(svg: Svg, width: int, x: float, y: float, w: float) -> float:
    h = 200 if width >= 768 else 240
    svg.group_open("section-bandeau-cta")
    svg.polygon("bg-bandeau-cta", [(x + 22, y), (x + w, y), (x + w - 54, y + h), (x, y + h)], fill=COLORS["navy"])
    if width >= 768:
        svg.rect("image-bandeau-cta-gauche", x - 34, y + 26, 48, 120, fill=COLORS["photo"], stroke="#bfd0eb", stroke_width=1.5, rx=12)
        svg.text("image-bandeau-cta-gauche-label", x - 28, y + 50, "image-bandeau-cta-gauche", size=11, fill=COLORS["navy"], family="mono")
    svg.text("texte-bandeau-cta", x + w * 0.34, y + 90, "texte-bandeau-cta", size=28 if width >= 1280 else 24 if width >= 768 else 20, fill="#ffffff", weight=700, anchor="middle")
    svg.text("texte-bandeau-cta-details", x + w * 0.72, y + 90, "texte-bandeau-cta-details", size=14, fill="#ffffff", family="mono", anchor="middle")
    if width >= 768:
        svg.polygon("decor-bandeau-cta-1", [(x + w - 86, y + h - 34), (x + w - 28, y + h - 14), (x + w - 60, y + h - 80)], fill=COLORS["navy_soft"])
        svg.polygon("decor-bandeau-cta-2", [(x + w - 132, y + h - 22), (x + w - 106, y + h + 12), (x + w - 96, y + h - 36)], fill=COLORS["salmon"])
    svg.group_close()
    return y + h


def draw_embedded(svg: Svg, width: int, x: float, y: float, w: float) -> float:
    stack = width < 768
    h = 500 if stack else 430
    svg.group_open("section-embedded")
    svg.group_open("logo-embedded")
    svg.text("logo-embedded-wordmark", x + w / 2, y + 56, "logo-embedded", size=34 if width >= 1280 else 28 if width >= 768 else 24, fill=COLORS["navy"], weight=700, anchor="middle")
    svg.group_close()
    col_w = w - 24 if stack else (w - 40) / 2
    left_x = x + 12
    right_x = x + 12 if stack else x + 28 + col_w
    first_y = y + 92
    draw_embedded_col(svg, "col-embedded-decouvrez", left_x, first_y, col_w, "titre-h2-embedded-decouvrez", "texte-embedded-decouvrez")
    second_y = first_y + 240 if stack else first_y
    draw_embedded_col(svg, "col-embedded-financez", right_x, second_y, col_w, "titre-h2-embedded-financez", "texte-embedded-financez")
    draw_button(svg, "button-labo", left_x + 24, first_y + 182, 170, 42, "Le Labo")
    svg.rect("image-cir", right_x + col_w - 140, second_y + 170, 112, 112, fill="#ffffff", stroke="#bfd0eb", stroke_width=1.5, rx=56)
    svg.text("image-cir-label", right_x + col_w - 84, second_y + 232, "image-cir", size=13, fill=COLORS["navy"], weight=700, anchor="middle", family="mono")
    svg.group_close()
    return y + h


def draw_embedded_col(svg: Svg, group_id: str, x: float, y: float, w: float, title_id: str, body_id: str) -> None:
    svg.group_open(group_id)
    svg.text(title_id, x + w / 2, y + 34, title_id, size=24, fill=COLORS["navy"], weight=700, anchor="middle")
    svg.text(body_id, x + 20, y + 86, body_id, size=14, fill=COLORS["text"], family="mono")
    svg.group_close()


def draw_valeurs(svg: Svg, width: int, x: float, y: float, w: float) -> float:
    h = 220
    svg.group_open("section-valeurs")
    svg.polygon("bg-valeurs", [(x, y), (x + w - 60, y), (x + w, y + h), (x, y + h)], fill=COLORS["navy"])
    centers = [x + w * 0.18, x + w * 0.33, x + w * 0.50, x + w * 0.67, x + w * 0.84]
    ids = [
        ("card-valeur-idees", "image-valeur-idees", "label-valeur-idees"),
        ("card-valeur-plus", "image-valeur-plus", ""),
        ("card-valeur-expertises", "image-valeur-expertises", "label-valeur-expertises"),
        ("card-valeur-equals", "image-valeur-equals", ""),
        ("card-valeur-aventure", "image-valeur-aventure", "label-valeur-aventure"),
    ]
    for idx, center in enumerate(centers):
        group_id, image_id, label_id = ids[idx]
        svg.group_open(group_id)
        svg.rect(image_id, center - 32, y + 38, 64, 64, fill=COLORS["photo"], stroke="#bfd0eb", stroke_width=1.5, rx=16)
        if label_id:
            svg.text(label_id, center, y + 152, label_id, size=17 if width >= 768 else 15, fill="#ffffff", weight=500, anchor="middle")
        else:
            svg.text(f"{image_id}-label", center, y + 84, image_id, size=13, fill=COLORS["navy"], family="mono", anchor="middle")
        svg.group_close()
    svg.group_close()
    return y + h


def draw_contact(svg: Svg, width: int, x: float, y: float, w: float) -> float:
    stack = width < 768
    h = 520 if stack else 430
    svg.group_open("section-contact-moi")
    image_w = 220
    image_h = 180
    image_x = x + (w - image_w) / 2
    svg.rect("image-contact-moi", image_x, y + 12, image_w, image_h, fill=COLORS["photo"], stroke="#bfd0eb", stroke_width=1.5, rx=22)
    title_y = y + 244
    svg.text("titre-h2-contact-moi", x + w / 2, title_y, "titre-h2-contact-moi", size=32 if width >= 1280 else 28 if width >= 768 else 24, fill=COLORS["salmon"], weight=700, anchor="middle")
    svg.text("texte-contact-telephone", x + w / 2, title_y + 44, "texte-contact-telephone", size=18, fill=COLORS["salmon"], anchor="middle")
    svg.text("texte-contact-mail", x + w / 2, title_y + 82, "texte-contact-mail", size=18, fill=COLORS["salmon"], anchor="middle")
    draw_button(svg, "button-mon-cv", x + (w - 180) / 2, title_y + 110, 180, 44, "Mon C.V")
    if _is_mobile(width):
        svg.text("contact-moi-mobile-note", x + w / 2, title_y + 172, "contact-moi-mobile-note", size=13, fill=COLORS["muted"], family="mono", anchor="middle")
    col_w = w - 24 if stack else (w - 44) / 2
    left_x = x + 12
    right_x = x + 12 if stack else x + 32 + col_w
    first_y = title_y + (204 if stack else 186)
    draw_contact_col_left(svg, left_x, first_y, col_w)
    second_y = first_y + 260 if stack else first_y
    draw_contact_col_right(svg, right_x, second_y, col_w)
    svg.polygon("decor-contact-moi-1", [(x + w - 92, y + h - 84), (x + w - 20, y + h - 72), (x + w - 40, y + h - 156)], fill=COLORS["navy_soft"])
    svg.polygon("decor-contact-moi-2", [(x + w - 112, y + h - 42), (x + w - 88, y + h + 12), (x + w - 66, y + h - 52)], fill=COLORS["salmon"])
    svg.group_close()
    return y + h


def draw_contact_col_left(svg: Svg, x: float, y: float, w: float) -> None:
    svg.group_open("col-contact-moi-gauche")
    svg.text("titre-h3-contact-moi-gauche", x + 8, y + 24, "titre-h3-contact-moi-gauche", size=18, fill=COLORS["navy"], weight=700, family="mono")
    svg.text("texte-contact-moi-gauche", x + 8, y + 60, "texte-contact-moi-gauche", size=16, fill=COLORS["salmon"], weight=600, family="mono")
    svg.text("texte-contact-moi-gauche-details", x + 8, y + 96, "texte-contact-moi-gauche-details", size=14, fill=COLORS["text"], family="mono")
    svg.group_close()


def draw_contact_col_right(svg: Svg, x: float, y: float, w: float) -> None:
    svg.group_open("col-contact-moi-droite")
    svg.text("texte-contact-moi-droite", x + 8, y + 24, "texte-contact-moi-droite", size=14, fill=COLORS["text"], family="mono")
    svg.text("titre-h4-contact-moi-droite", x + 8, y + 60, "titre-h4-contact-moi-droite", size=16, fill=COLORS["salmon"], weight=700, family="mono")
    svg.text("texte-contact-moi-droite-details", x + 8, y + 96, "texte-contact-moi-droite-details", size=14, fill=COLORS["text"], family="mono")
    svg.group_close()


def draw_footer(svg: Svg, width: int, x: float, y: float, w: float) -> float:
    stack = width < 768
    footer_h = 760 if stack else 520
    svg.group_open("footer")
    svg.rect("bg-footer", x, y + footer_h - 58, w, 58, fill=COLORS["navy"])
    svg.group_open("footer-bandeau-contact")
    photo_h = footer_h - 88
    svg.rect("bg-contact-photo", x, y, w, photo_h, fill=COLORS["photo"], stroke="#bfd0eb", stroke_width=1.5, rx=20)
    if stack:
        form_x = x + 16
        form_y = y + 16
        form_w = w - 32
        form_h = 340
        image_x = x + 16
        image_y = form_y + form_h + 18
        image_w = w - 32
        image_h = photo_h - form_h - 34
    else:
        image_x = x + 24
        image_y = y + 24
        image_w = w * 0.48
        image_h = photo_h - 48
        form_w = w * 0.34
        form_h = photo_h - 58
        form_x = x + w - form_w - 24
        form_y = y + 24
    svg.rect("image-contact-robot", image_x, image_y, image_w, image_h, fill="#e2ebf7", stroke="#bfd0eb", stroke_width=1.5, rx=18)
    svg.text("image-contact-robot-label", image_x + 18, image_y + 28, "image-contact-robot", size=14, fill=COLORS["navy"], family="mono")
    if not stack:
        svg.rect("image-contact-logo-droite", x + w - 184, y + 18, 140, 108, fill="#eef3fb", stroke="#bfd0eb", stroke_width=1.5, rx=16)
        svg.text("image-contact-logo-droite-label", x + w - 172, y + 46, "image-contact-logo-droite", size=10, fill=COLORS["navy"], family="mono")
    svg.group_open("contact-illu")
    svg.polygon("contact-illu-frame", [(image_x + 18, image_y + 24), (image_x + 170, image_y + 118), (image_x + 78, image_y + image_h - 24), (image_x + 18, image_y + image_h - 34)], fill=COLORS["navy"])
    svg.text("contact-illu-label", image_x + 86, image_y + 104, "contact-illu", size=18 if stack else 20, fill="#ffffff", weight=700, anchor="middle")
    svg.group_close()
    draw_footer_form(svg, form_x, form_y, form_w, form_h)
    svg.text("footer-text", x + w / 2, y + footer_h - 20, "footer-text", size=14, fill="#ffffff", anchor="middle", family="mono")
    svg.group_close()
    svg.group_close()
    return y + footer_h


def draw_footer_form(svg: Svg, x: float, y: float, w: float, h: float) -> None:
    svg.group_open("formulaire-contact-post")
    svg.rect("bg-contact-formulaire", x, y, w, h, fill=COLORS["navy"], rx=16)
    field_w = w - 40
    field_x = x + 20
    cursor_y = y + 20
    draw_input_group(svg, "input-nom-prenom-required", field_x, cursor_y, field_w, 44, "zone-nom-prenom", "placeholder-nom-prenom")
    cursor_y += 58
    draw_input_group(svg, "input-societe", field_x, cursor_y, field_w, 44, "zone-societe", "placeholder-societe")
    cursor_y += 58
    svg.group_open("ligne-contact")
    half_gap = 16
    half_w = (field_w - half_gap) / 2
    draw_input_group(svg, "input-telephone-required", field_x, cursor_y, half_w, 44, "zone-telephone", "placeholder-telephone")
    draw_input_group(svg, "input-mail-required", field_x + half_w + half_gap, cursor_y, half_w, 44, "zone-mail", "placeholder-mail")
    svg.group_close()
    cursor_y += 58
    svg.group_open("input-select-demande-required")
    svg.rect("zone-demande", field_x, cursor_y, field_w, 44, fill="#7486b4", rx=8)
    svg.text("option-choix-demande-selected", field_x + 14, cursor_y + 28, "option-choix-demande-selected", size=12, fill=COLORS["text"], family="mono")
    svg.text("option-demande-audit", field_x + field_w - 14, cursor_y + 18, "option-demande-audit", size=10, fill=COLORS["muted"], anchor="end", family="mono")
    svg.text("option-demande-expertise", field_x + field_w - 14, cursor_y + 30, "option-demande-expertise", size=10, fill=COLORS["muted"], anchor="end", family="mono")
    svg.text("option-demande-formation", field_x + field_w - 14, cursor_y + 42, "option-demande-formation", size=10, fill=COLORS["muted"], anchor="end", family="mono")
    svg.group_close()
    cursor_y += 58
    svg.group_open("input-message-required")
    svg.rect("zone-message", field_x, cursor_y, field_w, 126, fill="#7486b4", rx=8)
    svg.text("placeholder-message", field_x + 14, cursor_y + 28, "placeholder-message", size=12, fill=COLORS["text"], family="mono")
    svg.group_close()
    svg.text("action-contact", x + 20, y + h - 58, "action-contact", size=11, fill=COLORS["muted"], family="mono")
    draw_button(svg, "button-envoyer", x + 20, y + h - 44, 164, 38, "Envoyer")
    svg.group_close()


def draw_input_group(svg: Svg, group_id: str, x: float, y: float, w: float, h: float, zone_id: str, placeholder_id: str) -> None:
    svg.group_open(group_id)
    svg.rect(zone_id, x, y, w, h, fill="#7486b4", rx=8)
    svg.text(placeholder_id, x + 14, y + 28, placeholder_id, size=12, fill=COLORS["text"], family="mono")
    svg.group_close()


def draw_button(svg: Svg, group_id: str, x: float, y: float, w: float, h: float, label: str) -> None:
    svg.group_open(group_id)
    svg.polygon(f"bg-{group_id}", [(x + 18, y), (x + w, y), (x + w - 24, y + h), (x, y + h)], fill=COLORS["salmon"])
    svg.text(f"texte-{group_id}", x + w / 2, y + h * 0.68, label, size=18, fill="#ffffff", weight=700, anchor="middle")
    svg.group_close()


def write_board(paths: list[Path]) -> None:
    board_width = 2280
    board_height = 2800
    svg = Svg(board_width, board_height, "Responsive variant board")
    svg.rect("board-bg", 0, 0, board_width, board_height, fill=COLORS["page_bg"])
    svg.text("board-title", 80, 84, "Responsive Figma Variants", size=42, fill=COLORS["navy"], weight=700)
    svg.text("board-subtitle", 80, 122, "Board multi-largeurs pour tester le merge responsive par pages.", size=20, fill=COLORS["muted"])

    placements = [
        (80, 180, 960, 610, paths[0].name),
        (1160, 180, 640, 700, paths[1].name),
        (80, 920, 540, 820, paths[2].name),
        (700, 920, 360, 1320, paths[3].name),
    ]
    for idx, (x, y, w, h, label) in enumerate(placements, start=1):
        svg.rect(f"board-card-{idx}", x, y, w, h, fill="#fffdfa", stroke=COLORS["line"], stroke_width=2, rx=22)
        svg.text(f"board-label-{idx}", x + 24, y + 34, label, size=18, fill=COLORS["navy"], weight=700, family="mono")
    svg.write(DOCS_DIR / "responsive-variants-board.svg")


def main() -> None:
    written: list[Path] = []
    for variant in VARIANTS:
        svg = draw_variant(
            variant["width"],
            variant["page_width"],
            variant["page_height"],
            variant["label"],
        )
        path = DOCS_DIR / f"responsive-variant-{variant['width']}.svg"
        svg.write(path)
        written.append(path)
    write_board(written)
    print("Generated:")
    for path in written:
        print(f"- {path.name}")
    print("- responsive-variants-board.svg")


if __name__ == "__main__":
    main()
