import io
import json
import re
from pathlib import Path

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "templates" / "certificate.png"
GENERATED_DIR = PROJECT_ROOT / "generated"
LAYOUT_PATH = PROJECT_ROOT / "layout.json"
TEMPLATE_CONFIG_PATH = PROJECT_ROOT / "template_config.json"

def _ensure_generated_dir() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

def _sanitize_filename_component(value: str) -> str:
    value = value.strip()
    if not value:
        return "participant"
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", value)
    sanitized = sanitized.strip("_")
    return sanitized or "participant"

# ── DEFAULT LAYOUT ────────────────────────────────────────────
# ALL positions stored as RATIOS (0.0–1.0) relative to page size.
# font_size stored as a ratio relative to page WIDTH (e.g. 0.047 ≈ 40px on 850px canvas).
# max_width stored as a ratio relative to page WIDTH.
# This guarantees that any template size renders correctly.

def _default_layout() -> dict:
    return {
        "version": 2,
        "name_x": 0.5,          # 50% from left
        "name_y": 0.5,          # 50% from top
        "font_size": 0.047,     # ~40px on 850px canvas
        "font_family": "Helvetica-Bold",
        "color": "#000000",
        "max_width": 0.7,       # 70% of page width
    }

def load_layout() -> dict:
    """Load layout.json, merge with defaults, guarantee all fields present."""
    default = _default_layout()
    try:
        with open(LAYOUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default

    merged = {**default, **data}

    # ── Migrate legacy absolute-pixel layouts (version < 2) ──
    # If name_x or name_y > 1.0, they are old absolute pixel values.
    # Convert them to ratios assuming old canvas size 850×520.
    if merged.get("version", 1) < 2:
        if float(merged["name_x"]) > 1.0:
            merged["name_x"] = float(merged["name_x"]) / 850.0
        if float(merged["name_y"]) > 1.0:
            # ReportLab y=0 is bottom; canvas y=0 is top. Convert:
            merged["name_y"] = 1.0 - (float(merged["name_y"]) / 520.0)
        if float(merged["font_size"]) > 1.0:
            merged["font_size"] = float(merged["font_size"]) / 850.0
        if float(merged["max_width"]) > 1.0:
            merged["max_width"] = float(merged["max_width"]) / 850.0
        merged["version"] = 2

    return merged

def save_layout(layout: dict) -> dict:
    """Save complete layout to layout.json and return saved data."""
    data = {**_default_layout(), **layout}
    data["version"] = 2
    LAYOUT_PATH.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print(f"[LAYOUT SAVED] {data}")
    return data

def _hex_to_color(value: str) -> Color:
    v = str(value).strip()
    if not v.startswith("#"):
        v = "#" + v
    if len(v) == 4:
        v = "#" + "".join(ch * 2 for ch in v[1:])
    if len(v) != 7:
        return Color(0, 0, 0)
    try:
        r = int(v[1:3], 16) / 255.0
        g = int(v[3:5], 16) / 255.0
        b = int(v[5:7], 16) / 255.0
        return Color(r, g, b)
    except Exception:
        return Color(0, 0, 0)

def _get_reportlab_font(family: str) -> str:
    """Map font_family string to a valid built-in ReportLab font name."""
    # Direct ReportLab font names accepted as-is
    VALID_FONTS = {
        "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
        "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
        "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    }
    if family in VALID_FONTS:
        return family

    # Friendly name mapping
    lookup = {
        "Sans":             "Helvetica-Bold",
        "Serif":            "Times-Bold",
        "Mono":             "Courier-Bold",
        "sans-serif":       "Helvetica-Bold",
        "serif":            "Times-Bold",
        "monospace":        "Courier-Bold",
    }
    return lookup.get(family, "Helvetica-Bold")

def _fit_font_size(c: canvas.Canvas, text: str, font_name: str, desired_size: int, max_width: float) -> int:
    size = max(8, desired_size)
    if max_width <= 0:
        return size
    while size > 8:
        if c.stringWidth(text, font_name, size) <= max_width:
            return size
        size -= 1
    return 8

def render_certificate_pdf_bytes(name: str, layout: dict = None) -> bytes:
    """
    Render a certificate PDF to bytes using the saved (or provided) layout.
    All layout positions are stored as ratios (0–1) so they scale to any template size.
    """
    if layout is None:
        layout = load_layout()

    buf = io.BytesIO()

    # Get template dimensions
    if TEMPLATE_PATH.exists():
        from reportlab.lib import utils
        try:
            img = utils.ImageReader(str(TEMPLATE_PATH))
            img_width, img_height = img.getSize()
        except Exception:
            img_width, img_height = landscape(A4)
    else:
        img_width, img_height = landscape(A4)

    c = canvas.Canvas(buf, pagesize=(img_width, img_height))

    # Draw background
    if TEMPLATE_PATH.exists():
        c.drawImage(
            str(TEMPLATE_PATH), 0, 0,
            width=img_width, height=img_height,
            preserveAspectRatio=False, mask="auto",
        )
    else:
        c.setFillColor(Color(1, 1, 1))
        c.rect(0, 0, img_width, img_height, fill=1, stroke=0)

    # ── Read layout values ──
    font_name    = _get_reportlab_font(str(layout.get("font_family", "Helvetica-Bold")))
    x_ratio      = float(layout.get("name_x", 0.5))
    y_ratio      = float(layout.get("name_y", 0.5))
    size_ratio   = float(layout.get("font_size", 0.047))
    color_hex    = str(layout.get("color", "#000000"))
    width_ratio  = float(layout.get("max_width", 0.7))

    # ── Convert ratios → absolute PDF coordinates ──
    # X: from left edge of page
    pdf_x = x_ratio * img_width

    # Y: ReportLab origin is BOTTOM-LEFT, but y_ratio=0 means top of page in our system
    # So: pdf_y = (1 - y_ratio) * img_height
    pdf_y = (1.0 - y_ratio) * img_height

    # Font size as ratio of page width
    base_size    = max(8, int(size_ratio * img_width))
    max_width_px = width_ratio * img_width

    fitted_size = _fit_font_size(c, name, font_name, base_size, max_width_px)
    c.setFont(font_name, fitted_size)
    c.setFillColor(_hex_to_color(color_hex))

    print(f"[PDF RENDER] name={name!r} font={font_name} size={fitted_size} x={pdf_x:.1f} y={pdf_y:.1f} color={color_hex}")

    c.drawCentredString(pdf_x, pdf_y, name)
    c.showPage()
    c.save()
    return buf.getvalue()

def generate_certificate(name: str, email: str, display_name: str = None) -> str:
    """Generate a PDF certificate and return its file path."""
    _ensure_generated_dir()
    printed_name = (display_name or name).strip() or name
    safe_name = _sanitize_filename_component(name)
    email_local = email.split("@")[0] if "@" in email else email
    safe_email = _sanitize_filename_component(email_local)
    filename = f"{safe_name}_{safe_email}.pdf"
    output_path = GENERATED_DIR / filename
    pdf_bytes = render_certificate_pdf_bytes(printed_name)
    output_path.write_bytes(pdf_bytes)
    print(f"[CERT GENERATED] {output_path}")
    return str(output_path)
