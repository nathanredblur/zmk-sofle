#!/usr/bin/env python3
"""
Post-processor that injects a rich legend into the keymap-drawer SVG.

The legend includes:
  - A key-anatomy diagram (one sample key with arrows pointing to tap / shifted /
    hold zones, plus a two-key combo example).
  - Layer navigation cheat sheet (how to switch between Base, Nav, Fn, Conf).
  - Key color legend (what the red / teal / gray backgrounds mean).
  - Icon glossary with the actual MDI glyphs referenced via <use>.
  - RGB control explanation (HUI, HUD, SAI, SAD, etc.).
  - macOS modifier glyphs.
  - Spanish accent typing (ñ / é macros).

We do all of this in Python because keymap-drawer's `footer_text` field ends up
inside a `<text>` element, which by SVG spec cannot contain `<use>`. By
post-processing the SVG we get full freedom to mix icons, shapes, and text.
"""
from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Legend content
# ---------------------------------------------------------------------------

@dataclass
class IconRow:
    icon: str         # mdi:* id (must already exist in the SVG <defs>)
    label: str        # short bold label
    desc: str         # description / explanation


ICON_GLOSSARY: list[IconRow] = [
    IconRow("mdi:power-sleep",       "soft-off",     "Turn the keyboard off (deep sleep). Lives in the Conf layer."),
    IconRow("mdi:cog",               "Conf",         "Toggle the Configurations layer (BT, RGB, reset, etc.)."),
    IconRow("mdi:backup-restore",    "sys-reset",    "Reboot the ZMK firmware (soft reset)."),
    IconRow("mdi:progress-download", "bootloader",   "Enter bootloader mode to flash new firmware."),
    IconRow("mdi:alpha-w-box",       "caps-word",    "One-shot CAPS: types in uppercase until you press space."),
    IconRow("mdi:gesture-tap-hold",  "sticky",       "Sticky modifier: tap once, it applies to the next keypress."),
    IconRow("mdi:bluetooth-connect", "BT select",    "Choose a Bluetooth profile slot. Shift shows the slot number."),
    IconRow("mdi:bluetooth-off",     "BT clear",     "Forget the current Bluetooth pairing."),
    IconRow("mdi:usb",               "USB out",      "Force keyboard output through the USB cable instead of BT."),
    IconRow("mdi:toggle-switch",     "OUT_TOG",      "Toggle the active output between USB and Bluetooth."),
    IconRow("mdi:led-on",            "RGB on",       "Toggle the RGB underglow on / off."),
    IconRow("mdi:palette",           "RGB effect",   "Cycle to the next animation effect (Shift = previous)."),
    IconRow("mdi:format-color-fill", "RGB hue",      "Move the color wheel position. H+ forward, H- backward."),
    IconRow("mdi:invert-colors",     "RGB sat.",     "Saturation. S+ deeper color, S- towards white."),
    IconRow("mdi:speedometer",       "RGB speed",    "Animation speed (Shift = slow it down)."),
    IconRow("mdi:brightness-5",      "RGB bright",   "Underglow brightness. Hold label shows B+ or B-."),
    IconRow("mdi:mouse-left-click-outline",  "LCLK",  "Left mouse click."),
    IconRow("mdi:mouse-right-click-outline", "RCLK",  "Right mouse click."),
    IconRow("mdi:mouse-scroll-wheel",        "MCLK",  "Middle mouse click (scroll-wheel press)."),
    IconRow("mdi:mouse-move-up",     "MB4",          "Mouse back button (browser history back)."),
    IconRow("mdi:mouse-move-down",   "MB5",          "Mouse forward button (browser history forward)."),
    IconRow("mdi:mouse",             "mmv",          "Pointer movement (arrows on the joystick keys in Nav)."),
    IconRow("mdi:camera",            "Screenshot",   "macOS screenshot tool (Cmd+Shift+5): record, markup, etc."),
    IconRow("mdi:crop-free",         "Region",       "macOS region capture (Cmd+Shift+4). Hold \u2192 to clipboard."),
    IconRow("mdi:ocr",               "Full shot",    "macOS full-screen capture (Cmd+Shift+3)."),
    IconRow("mdi:transfer",          "trans",        "Transparent key: falls through to the Base layer's binding."),
    IconRow("mdi:minus-circle-outline", "none",      "No binding on this key for this layer."),
]


LAYER_NAV_ROWS: list[tuple[str, str]] = [
    ("Base \u2192 Nav",       "Hold the LEFT thumb cluster key (mo 1)."),
    ("Base \u2192 Fn",        "Hold the RIGHT thumb cluster key (mo 2)."),
    ("Base \u2192 Conf",      "Combo Esc + 1 (top-left). Look for the gear icon."),
    ("Any  \u2192 caps-word", "Press both Shifts together (outer pinky on each side)."),
    ("Type \u00f1",                "Hold the SEMI (;) key (right pinky home, hold action)."),
    ("Type \u00e9",                "Hold the APOS (') key (right pinky outer, hold action)."),
]


COLOR_ROWS: list[tuple[str, str, str]] = [
    ("#e57373", "Red \u2014 Esc/Caps",        "Tap = Esc, Hold = Caps Lock. Always visible, pulses subtly."),
    ("#80cbc4", "Teal \u2014 Thumb cluster",  "Layer activators (mo 1 = Nav, mo 2 = Fn)."),
    ("#cfd8dc", "Gray \u2014 Edges",          "Outer columns, pinkies, rotary encoders, rocker."),
]


RGB_ACRONYMS: list[tuple[str, str]] = [
    ("TOG / ON / OFF", "Turn the RGB underglow on, off, or toggle."),
    ("EFF / EFR",      "Next / previous animation effect (rainbow, breathe, etc.)."),
    ("SPI",            "Animation speed up. Shift = slow it down."),
    ("BRI / BRD",      "Brightness up / down."),
    ("HUI / HUD",      "HUE up / down \u2014 rotate the color wheel position."),
    ("SAI / SAD",      "SATURATION up / down \u2014 SAD = white-ish, SAI = vivid color."),
]


MAC_MODS = "\u2318 Cmd   \u2325 Option   \u2303 Control   \u21e7 Shift   \u21ea Caps Lock   \u238b Escape"


SPANISH_NOTE_LINES = [
    "Two-step dead-key flow (macOS US layout):",
    "  1. HOLD SEMI (;) to send Option+N \u2014 arms the tilde dead key (~).",
    "     HOLD APOS (') to send Option+E \u2014 arms the acute dead key (\u00b4).",
    "  2. Release, then TAP a vowel: n \u2192 \u00f1, a/e/i/o/u \u2192 \u00e1 / \u00e9 / \u00ed / \u00f3 / \u00fa.",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_available_icons(svg: str) -> set[str]:
    """Return the set of mdi:* glyph IDs already defined in <defs>."""
    return set(re.findall(r'<svg id="(mdi:[^"]+)"', svg))


def get_svg_dims(svg: str) -> tuple[int, int, int]:
    m = re.search(r'<svg[^>]*\swidth="(\d+)"[^>]*\sheight="(\d+)"[^>]*viewBox="0 0 (\d+) (\d+)"', svg)
    if not m:
        raise SystemExit("could not parse svg root dimensions")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def find_legend_y(svg: str, fallback_height: int) -> int:
    """Find the y position right after the last layer in the SVG."""
    last = None
    for m in re.finditer(r'<g transform="translate\(0,\s*(\d+)\)" class="layer-', svg):
        last = int(m.group(1))
    if last is None:
        return fallback_height
    # Each layer is roughly 565px tall (with our outer_pad_h=90). Add a small margin.
    return last + 600


def icon_use(icon_id: str, x: float, y: float, size: int = 26) -> str:
    if not icon_id:
        return ""
    return (
        f'<use href="#{icon_id}" xlink:href="#{icon_id}" '
        f'x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" class="legend-icon glyph"/>'
    )


def text(x: float, y: float, content: str, cls: str = "legend-item") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}">{html.escape(content)}</text>'


def divider(x: float, y: float, length: float) -> str:
    return f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + length:.1f}" y2="{y:.1f}" class="legend-divider"/>'


def section_title(x: float, y: float, label: str) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="legend-section">{html.escape(label)}</text>'


def card(x: float, y: float, w: float, h: float) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" class="legend-card"/>'


# ---------------------------------------------------------------------------
# Key-anatomy diagram (sample key with arrows)
# ---------------------------------------------------------------------------

def render_anatomy(origin_x: float, origin_y: float) -> tuple[str, float]:
    """
    Draws a sample key and a 2-key combo, with arrows pointing to each annotation.
    Returns (svg_markup, height_consumed).
    """
    parts: list[str] = []

    parts.append(section_title(origin_x, origin_y, "Key anatomy"))

    # Sample key dimensions
    key_x, key_y, key_w, key_h = origin_x + 220, origin_y + 50, 110, 110

    # The sample key itself: red so it pops, mimicking the Esc/Caps cap.
    parts.append(
        f'<g class="key keypos-anatomy-sample">'
        f'<rect x="{key_x}" y="{key_y}" rx="6" ry="6" width="{key_w}" height="{key_h}" '
        f'fill="#e57373" stroke="#ef9a9a" stroke-width="2"/>'
        # shifted label (top)
        f'<text x="{key_x + 14}" y="{key_y + 22}" font-size="12" fill="#37474f">!</text>'
        # tap label (center)
        f'<text x="{key_x + key_w / 2}" y="{key_y + key_h / 2 + 6}" font-size="22" font-weight="700" '
        f'fill="#263238" text-anchor="middle">1</text>'
        # hold label (bottom)
        f'<text x="{key_x + 14}" y="{key_y + key_h - 10}" font-size="12" fill="#37474f">Esc</text>'
        f'</g>'
    )

    # Arrows + descriptions
    label_x = key_x + key_w + 60
    arrows = [
        # (start_x, start_y, end_x, end_y, label_x, label_y, label_text)
        (key_x + 22,         key_y + 18,             label_x - 10, key_y + 12,
         label_x,           key_y + 16,
         "shifted action  \u2014 sent when you also hold Shift"),
        (key_x + key_w / 2,  key_y + key_h / 2,      label_x - 10, key_y + key_h / 2 - 2,
         label_x,           key_y + key_h / 2 + 4,
         "tap action  \u2014 what you get with a quick press"),
        (key_x + 28,         key_y + key_h - 14,     label_x - 10, key_y + key_h - 14,
         label_x,           key_y + key_h - 10,
         "hold action  \u2014 sent when you hold the key (mod-tap)"),
    ]
    for sx, sy, ex, ey, lx, ly, lbl in arrows:
        parts.append(
            f'<path d="M{sx},{sy} L{ex},{ey}" class="legend-arrow"/>'
            f'<text x="{lx}" y="{ly}" class="legend-arrow-text">{html.escape(lbl)}</text>'
        )

    # The smaller two-key combo example below the main sample
    combo_y = key_y + key_h + 60
    cw, ch = 64, 64
    c1_x, c2_x = key_x - 40, key_x + 110
    parts.append(
        # two ghost keys
        f'<rect x="{c1_x}" y="{combo_y}" rx="5" ry="5" width="{cw}" height="{ch}" fill="#eceff1" stroke="#cfd8dc"/>'
        f'<rect x="{c2_x}" y="{combo_y}" rx="5" ry="5" width="{cw}" height="{ch}" fill="#eceff1" stroke="#cfd8dc"/>'
        f'<text x="{c1_x + cw / 2}" y="{combo_y + ch / 2 + 8}" font-size="22" font-weight="700" '
        f'fill="#263238" text-anchor="middle">L</text>'
        f'<text x="{c2_x + cw / 2}" y="{combo_y + ch / 2 + 8}" font-size="22" font-weight="700" '
        f'fill="#263238" text-anchor="middle">;</text>'
        # combo box between them with dendrons
        f'<path d="M{c1_x + cw},{combo_y + ch / 2} L{c2_x},{combo_y + ch / 2}" '
        f'stroke="#cfd8dc" stroke-width="2" fill="none"/>'
        f'<rect x="{(c1_x + cw + c2_x) / 2 - 18}" y="{combo_y + ch / 2 - 16}" '
        f'rx="4" ry="4" width="36" height="32" fill="#fff59d" stroke="#f9a825"/>'
        f'<text x="{(c1_x + cw + c2_x) / 2}" y="{combo_y + ch / 2 + 4}" font-size="16" font-weight="700" '
        f'fill="#5d4037" text-anchor="middle">\u00e9</text>'
    )
    parts.append(
        f'<path d="M{(c1_x + cw + c2_x) / 2 + 28},{combo_y + ch / 2} L{label_x - 10},{combo_y + ch / 2}" class="legend-arrow"/>'
        f'<text x="{label_x}" y="{combo_y + ch / 2 + 5}" class="legend-arrow-text">'
        f'combo  \u2014 press both keys at once to produce the small yellow box\'s value</text>'
    )

    return "\n".join(parts), combo_y + ch + 30 - origin_y


# ---------------------------------------------------------------------------
# Section renderers (return svg, height)
# ---------------------------------------------------------------------------

def render_layer_nav(x: float, y: float, width: float) -> tuple[str, float]:
    parts: list[str] = [section_title(x, y, "Layer navigation")]
    cy = y + 30
    for label, desc in LAYER_NAV_ROWS:
        parts.append(text(x, cy, label, cls="legend-row"))
        # label is rendered in plain class; we want bold + desc lighter
        # use a separate row text with tspans for nicer styling
        parts[-1] = (
            f'<text x="{x:.1f}" y="{cy:.1f}" class="legend-row">'
            f'<tspan class="label">{html.escape(label)}</tspan>'
            f'<tspan class="desc" dx="14">{html.escape(desc)}</tspan>'
            f'</text>'
        )
        cy += 24
    return "\n".join(parts), cy - y + 12


def render_colors(x: float, y: float, width: float) -> tuple[str, float]:
    parts: list[str] = [section_title(x, y, "Key colors")]
    cy = y + 30
    for fill, label, desc in COLOR_ROWS:
        parts.append(
            f'<rect x="{x:.1f}" y="{cy - 18:.1f}" width="22" height="22" rx="4" ry="4" fill="{fill}" stroke="#b0bec5"/>'
            f'<text x="{x + 36:.1f}" y="{cy:.1f}" class="legend-row">'
            f'<tspan class="label">{html.escape(label)}</tspan>'
            f'<tspan class="desc" dx="10">{html.escape(desc)}</tspan>'
            f'</text>'
        )
        cy += 30
    return "\n".join(parts), cy - y + 8


def render_icon_glossary(x: float, y: float, width: float, available_icons: set[str]) -> tuple[str, float]:
    parts: list[str] = [section_title(x, y, "Icon glossary")]
    cy = y + 36
    row_h = 30
    col_w = width / 2
    # Filter to icons that actually exist in the SVG (avoid broken <use> refs).
    rows = [r for r in ICON_GLOSSARY if r.icon in available_icons]
    # Two-column layout: fill left column then right.
    n = len(rows)
    half = (n + 1) // 2
    for idx, row in enumerate(rows):
        col = 0 if idx < half else 1
        i = idx if col == 0 else idx - half
        rx = x + col * col_w
        ry = cy + i * row_h
        parts.append(icon_use(row.icon, rx, ry - 20, size=24))
        parts.append(
            f'<text x="{rx + 36:.1f}" y="{ry:.1f}" class="legend-row">'
            f'<tspan class="label">{html.escape(row.label)}</tspan>'
            f'<tspan class="desc" dx="10">{html.escape(row.desc)}</tspan>'
            f'</text>'
        )
    block_h = half * row_h + 50
    return "\n".join(parts), block_h


def render_rgb(x: float, y: float, width: float) -> tuple[str, float]:
    parts: list[str] = [section_title(x, y, "RGB controls")]
    cy = y + 30
    for label, desc in RGB_ACRONYMS:
        parts.append(
            f'<text x="{x:.1f}" y="{cy:.1f}" class="legend-row">'
            f'<tspan class="label">{html.escape(label)}</tspan>'
            f'<tspan class="desc" dx="14">{html.escape(desc)}</tspan>'
            f'</text>'
        )
        cy += 24
    return "\n".join(parts), cy - y + 12


def render_mac_mods(x: float, y: float, width: float) -> tuple[str, float]:
    parts: list[str] = [section_title(x, y, "macOS modifiers")]
    parts.append(text(x, y + 32, MAC_MODS, cls="legend-row"))
    return "\n".join(parts), 60


def render_spanish(x: float, y: float, width: float) -> tuple[str, float]:
    parts: list[str] = [section_title(x, y, "Spanish accents (macOS)")]
    parts.append(
        f'<text x="{x:.1f}" y="{y + 32:.1f}" class="legend-row">'
        f'<tspan class="label">~</tspan>'
        f'<tspan class="desc" dx="12">HOLD SEMI (;) \u2014 then tap N for \u00f1 (right pinky home)</tspan>'
        f'</text>'
    )
    parts.append(
        f'<text x="{x:.1f}" y="{y + 56:.1f}" class="legend-row">'
        f'<tspan class="label">\u00b4</tspan>'
        f'<tspan class="desc" dx="12">HOLD APOS (\u2019) \u2014 then tap E for \u00e9 (right pinky outer)</tspan>'
        f'</text>'
    )
    # Wrap the long note across multiple lines (SVG <text> doesn't auto-wrap).
    note_y = y + 84
    for i, line in enumerate(SPANISH_NOTE_LINES):
        parts.append(
            f'<text x="{x:.1f}" y="{note_y + i * 18:.1f}" class="legend-note">'
            f'{html.escape(line)}'
            f'</text>'
        )
    total_h = 84 + len(SPANISH_NOTE_LINES) * 18 + 8
    return "\n".join(parts), total_h


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_legend(width: int, available_icons: set[str]) -> tuple[str, int]:
    pad = 40
    inner_w = width - 2 * pad
    col_gap = 40
    col_w = (inner_w - col_gap) / 2

    blocks: list[str] = []
    y = 30  # local y inside the legend group

    # Title
    blocks.append(f'<text x="{pad}" y="{y + 12}" class="legend-title">Legend</text>')
    y += 56
    blocks.append(divider(pad, y, inner_w))
    y += 18

    # Row 1: key anatomy (full width)
    anatomy, anatomy_h = render_anatomy(pad, y)
    blocks.append(anatomy)
    y += anatomy_h + 20
    blocks.append(divider(pad, y, inner_w))
    y += 18

    # Row 2: layer nav (left)  +  colors (right)
    nav, nav_h = render_layer_nav(pad, y, col_w)
    colors, colors_h = render_colors(pad + col_w + col_gap, y, col_w)
    blocks.append(nav)
    blocks.append(colors)
    y += max(nav_h, colors_h) + 20
    blocks.append(divider(pad, y, inner_w))
    y += 18

    # Row 3: icon glossary (full width)
    glossary, glossary_h = render_icon_glossary(pad, y, inner_w, available_icons)
    blocks.append(glossary)
    y += glossary_h + 20
    blocks.append(divider(pad, y, inner_w))
    y += 18

    # Row 4: rgb (left)  +  mac mods + spanish (right stacked)
    rgb, rgb_h = render_rgb(pad, y, col_w)
    mac, mac_h = render_mac_mods(pad + col_w + col_gap, y, col_w)
    spa, spa_h = render_spanish(pad + col_w + col_gap, y + mac_h + 10, col_w)
    right_total = mac_h + 10 + spa_h
    blocks.append(rgb)
    blocks.append(mac)
    blocks.append(spa)
    y += max(rgb_h, right_total) + 24

    total_height = int(y) + 20

    # Arrowhead marker
    marker_def = (
        '<defs><marker id="legend-arrowhead" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#ab47bc"/></marker></defs>'
    )

    legend_inner = marker_def + "\n" + "\n".join(blocks)
    return legend_inner, total_height


def parse_combo_positions(yaml_path: Path) -> list[list[int]]:
    """
    Cheap parser for the combos section of the keymap-drawer YAML. Returns the
    list of `p: [...]` arrays in the order they appear (which matches the
    order of `<g class="combo combopos-N">` groups in the SVG).

    We avoid pulling in a YAML library so the post-processor stays dependency-free.
    """
    if not yaml_path.exists():
        return []
    inside = False
    positions: list[list[int]] = []
    for line in yaml_path.read_text().splitlines():
        stripped = line.rstrip()
        if not inside:
            if stripped == "combos:":
                inside = True
            continue
        # End of combos block: any non-indented, non-empty line that isn't part
        # of the list (i.e. starts a new top-level YAML key like `layers:`).
        if stripped and not line.startswith((" ", "\t", "-")):
            break
        m = re.match(r'-\s*p:\s*\[([^\]]+)\]', stripped)
        if m:
            positions.append([int(n) for n in re.findall(r'-?\d+', m.group(1))])
    return positions


# Combos whose dendron columns line up vertically with another combo and would
# render right on top of each other. Each entry shifts that combo group
# horizontally by N pixels so the two stacks become visually distinct.
# Keyed by the frozen-set of involved positions so reordering the keymap doesn't
# break the lookup.
COMBO_NUDGE_X: dict[frozenset[int], int] = {
    frozenset((18, 20)): -16,  # back_pipe (T+Y) — shift left of pipe (G+H, same cols)
}


def inject_combo_data_keys(svg: str, combo_positions: list[list[int]]) -> str:
    """
    Add `data-keys="p1,p2,..."` to each `<g class="combo combopos-N">` so the
    HTML viewer can highlight the linked keys on hover. Also apply any
    `COMBO_NUDGE_X` horizontal shifts so overlapping combo dendrons are visible.
    """
    if not combo_positions:
        return svg

    def replacement(match: re.Match) -> str:
        idx = int(match.group(1))
        if idx >= len(combo_positions):
            return match.group(0)
        positions = combo_positions[idx]
        keys = ",".join(str(p) for p in positions)
        nudge = COMBO_NUDGE_X.get(frozenset(positions), 0)
        transform = f' transform="translate({nudge}, 0)"' if nudge else ""
        return f'<g class="combo combopos-{idx}" data-keys="{keys}"{transform}>'

    return re.sub(r'<g class="combo combopos-(\d+)">', replacement, svg)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: generate_legend.py <svg_path>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    svg = path.read_text()

    # 1. Remove any pre-existing footer text element.
    svg = re.sub(r'<text[^>]*class="footer"[^>]*>.*?</text>\s*', '', svg, flags=re.S)

    # 1b. Inject `data-keys` so the HTML viewer can highlight involved keys on hover.
    combo_positions = parse_combo_positions(path.with_suffix(".yaml"))
    svg = inject_combo_data_keys(svg, combo_positions)

    # 2. Inspect dimensions and icons.
    width, height, viewbox_h = get_svg_dims(svg)
    available_icons = find_available_icons(svg)
    if not available_icons:
        print("warning: no mdi icons found in <defs>; legend will lack glyphs", file=sys.stderr)

    # 3. Compute where to place the legend.
    legend_y = find_legend_y(svg, height)

    # 4. Build the legend SVG.
    legend_inner, legend_h = build_legend(width, available_icons)
    legend_block = (
        f'<g transform="translate(0, {legend_y})" class="legend">\n'
        f'{legend_inner}\n'
        f'</g>\n'
    )

    # 5. Insert before the closing </svg>.
    close_pos = svg.rfind('</svg>')
    svg = svg[:close_pos] + legend_block + svg[close_pos:]

    # 6. Update SVG dimensions to contain the legend.
    new_height = legend_y + legend_h + 30
    svg = re.sub(r'(<svg[^>]*\sheight=")(\d+)(")', lambda m: f'{m.group(1)}{new_height}{m.group(3)}', svg, count=1)
    svg = re.sub(
        r'(<svg[^>]*viewBox="0 0 \d+ )(\d+)(")',
        lambda m: f'{m.group(1)}{new_height}{m.group(3)}',
        svg,
        count=1,
    )

    path.write_text(svg)
    print(f"Legend injected ({len(available_icons)} icons available, total svg height {new_height}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
