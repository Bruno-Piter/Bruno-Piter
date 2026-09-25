#!/usr/bin/env python3
"""Gera o cartão animado do perfil: retrato, React, C# e floco de neve.

Saída: assets/visual-dark.svg e assets/visual-light.svg
Foto de origem: assets/portrait.jpg
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "assets" / "portrait.jpg"
ICONS = ROOT / "assets" / "icons"
OUT_DARK = ROOT / "assets" / "visual-dark.svg"
OUT_LIGHT = ROOT / "assets" / "visual-light.svg"
PREVIEW = Path(os.environ.get("TEMP", ".")) / "banner-previews"

W, H = 520, 680
COLS = 180
TRAVELLERS = 640
GROUPS = 64
DUR = 14.2
# portrait 3.0s, transição 1.3s, cada ícone 2.0s
MARKS = [0.0, 3.0, 4.3, 6.3, 7.6, 9.6, 10.9, 12.9, 14.2]
LOGO_SPAN = 0.74
DRIFT = 0.42
NOISE = 6.0
SEED = 7

FRAME = {"x": 16, "y": 54, "w": W - 32, "h": H - 70}
AREA = {
    "x": FRAME["x"] + 14,
    "y": FRAME["y"] + 34,
    "w": FRAME["w"] - 28,
    "h": FRAME["h"] - 48,
}

THEMES = {
    "dark": {
        "bg": "#070B16",
        "panel": "#0C1428",
        "cyan": "#22D3EE",
        "violet": "#C4B5FD",
        "text": "#E2E8F0",
        "muted": "#94A3B8",
        "dim": "#64748B",
        "stroke": "rgba(34,211,238,0.55)",
        "frame": "rgba(34,211,238,0.32)",
        "live": "#FB7185",
        "rgb": (196, 181, 253),
        "bg_rgb": (7, 11, 22),
        "panel_rgb": (12, 20, 40),
        "cyan_rgb": (34, 211, 238),
    },
    "light": {
        "bg": "#F8FAFC",
        "panel": "#FFFFFF",
        "cyan": "#0891B2",
        "violet": "#6D28D9",
        "text": "#0F172A",
        "muted": "#475569",
        "dim": "#94A3B8",
        "stroke": "rgba(8,145,178,0.5)",
        "frame": "rgba(8,145,178,0.35)",
        "live": "#E11D48",
        "rgb": (109, 40, 217),
        "bg_rgb": (248, 250, 252),
        "panel_rgb": (255, 255, 255),
        "cyan_rgb": (8, 145, 178),
    },
}

FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"


def rows_for(cols: int) -> int:
    return max(1, round(cols * AREA["h"] / AREA["w"]))


def floyd_steinberg(gray: np.ndarray) -> np.ndarray:
    """gray em 0..1 (1 = branco). Devolve True onde há tinta."""
    img = gray.astype(np.float64).copy()
    h, w = img.shape
    out = np.zeros((h, w), dtype=bool)
    for y in range(h):
        forward = y % 2 == 0
        xs = range(w) if forward else range(w - 1, -1, -1)
        step = 1 if forward else -1
        for x in xs:
            old = img[y, x]
            new = 1.0 if old >= 0.5 else 0.0
            out[y, x] = new < 0.5
            err = old - new
            xn = x + step
            if 0 <= xn < w:
                img[y, xn] += err * 7 / 16
            if y + 1 < h:
                img[y + 1, x] += err * 5 / 16
                xb = x - step
                if 0 <= xb < w:
                    img[y + 1, xb] += err * 3 / 16
                if 0 <= xn < w:
                    img[y + 1, xn] += err * 1 / 16
    return out


def subject_mask(rgb: np.ndarray) -> np.ndarray:
    corners = np.stack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]]).astype(np.float64)
    bg = np.median(corners, axis=0)
    dist = np.linalg.norm(rgb.astype(np.float64) - bg, axis=2)
    mask = dist > 26
    mask = ndimage.binary_closing(mask, iterations=2)
    mask = ndimage.binary_fill_holes(mask)
    labels, count = ndimage.label(mask)
    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        mask = labels == sizes.argmax()
    return mask


def crop_box(mask: np.ndarray, aspect: float) -> tuple[float, float, float, float]:
    ys, xs = np.nonzero(mask)
    y0, y1 = float(ys.min()), float(ys.max() + 1)
    x0, x1 = float(xs.min()), float(xs.max() + 1)
    # menos camisa, para o rosto ocupar o cartão
    y1 = y0 + (y1 - y0) * 0.72
    pad_x = (x1 - x0) * 0.05
    pad_top = (y1 - y0) * 0.045
    pad_bot = (y1 - y0) * 0.03
    y0 -= pad_top
    y1 += pad_bot
    x0 -= pad_x
    x1 += pad_x
    h = y1 - y0
    w = x1 - x0
    if w / h < aspect:
        grow = (h * aspect - w) / 2
        x0 -= grow
        x1 += grow
    else:
        # corta as laterais em vez de criar faixa vazia acima da cabeça
        keep = h * aspect
        cut = (w - keep) / 2
        x0 += cut
        x1 -= cut
    return y0, x0, y1, x1


def take_crop(arr: np.ndarray, box, fill):
    y0, x0, y1, x1 = box
    h, w = arr.shape[:2]
    oh = max(1, int(round(y1 - y0)))
    ow = max(1, int(round(x1 - x0)))
    if arr.ndim == 2:
        out = np.full((oh, ow), fill, dtype=arr.dtype)
    else:
        out = np.full((oh, ow, arr.shape[2]), fill, dtype=arr.dtype)
    sy0 = max(0, int(math.floor(y0)))
    sx0 = max(0, int(math.floor(x0)))
    sy1 = min(h, int(math.ceil(y1)))
    sx1 = min(w, int(math.ceil(x1)))
    dy0 = sy0 - int(math.floor(y0))
    dx0 = sx0 - int(math.floor(x0))
    patch = arr[sy0:sy1, sx0:sx1]
    y_end = min(oh, dy0 + patch.shape[0])
    x_end = min(ow, dx0 + patch.shape[1])
    out[dy0:y_end, dx0:x_end] = patch[: y_end - dy0, : x_end - dx0]
    return out


def load_portrait(cols: int, rows: int):
    im = Image.open(PHOTO).convert("RGBA")
    base = Image.new("RGBA", im.size, (255, 255, 255, 255))
    rgb = np.asarray(Image.alpha_composite(base, im).convert("RGB"))
    mask = subject_mask(rgb)
    aspect = cols / rows
    y0, x0, y1, x1 = crop_box(mask, aspect)
    # crop_box last return was messy if I wrote a bug — recompute cleanly below
    crop_rgb = take_crop(rgb, (y0, x0, y1, x1), 255)
    crop_mask = take_crop(mask, (y0, x0, y1, x1), False)
    pic = Image.fromarray(crop_rgb.astype(np.uint8), "RGB")
    pic = ImageOps.autocontrast(pic, cutoff=1)
    pic = ImageEnhance.Contrast(pic).enhance(1.28)
    pic = pic.filter(ImageFilter.UnsharpMask(radius=2, percent=130, threshold=2))
    small = pic.resize((cols, rows), Image.Resampling.LANCZOS)
    mask_im = Image.fromarray(crop_mask.astype(np.uint8) * 255).resize(
        (cols, rows), Image.Resampling.NEAREST
    )
    mask_small = np.asarray(mask_im) > 127
    arr = np.asarray(small).astype(np.float64)
    gray = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]) / 255.0
    gray = tone_curve(gray)
    gray[~mask_small] = 1.0
    dots = floyd_steinberg(gray) & mask_small
    return dots, small, mask_small


def tone_curve(gray: np.ndarray) -> np.ndarray:
    """Mantém cabelo, barba e camisa escuros; abre a pele em pontos."""
    # cabelo e camisa continuam escuros; a pele fica no meio, com grão
    pivot = 0.20
    out = gray.copy()
    dark = gray <= pivot
    out[dark] = gray[dark] * 0.75
    light = ~dark
    span = 0.62
    t = np.clip((gray[light] - pivot) / span, 0, 1)
    out[light] = 0.50 + 0.24 * t
    white = gray >= 0.90
    out[white] = 1.0
    return np.clip(out, 0, 1)


def grid_geometry(cols: int, rows: int):
    pitch = min(AREA["w"] / cols, AREA["h"] / rows)
    grid_w = cols * pitch
    grid_h = rows * pitch
    ox = AREA["x"] + (AREA["w"] - grid_w) / 2
    oy = AREA["y"] + (AREA["h"] - grid_h) / 2
    return pitch, ox, oy


def dot_points(dots: np.ndarray, pitch: float, ox: float, oy: float):
    ys, xs = np.nonzero(dots)
    top = np.column_stack([ox + xs * pitch, oy + ys * pitch])
    centers = top + pitch / 2
    return top, centers


def ink_png(path: Path) -> np.ndarray:
    arr = np.asarray(Image.open(path).convert("RGBA"))
    ink = arr[:, :, 3] > 128
    if int(ink.sum()) < 200:
        raise SystemExit(f"pouca tinta em {path}")
    return ink


def csharp_mask(n: int = 720) -> np.ndarray:
    im = Image.new("L", (n, n), 0)
    draw = ImageDraw.Draw(im)
    stroke = max(10, int(n * 0.085))
    box = [n * 0.06, n * 0.10, n * 0.64, n * 0.90]
    draw.arc(box, start=45, end=315, fill=255, width=stroke)
    bar = max(8, int(n * 0.045))
    x0, x1 = n * 0.70, n * 0.94
    y0, y1 = n * 0.30, n * 0.70
    for t in (0.30, 0.70):
        x = x0 + (x1 - x0) * t
        draw.line((x, y0, x, y1), fill=255, width=bar)
    for t in (0.34, 0.66):
        y = y0 + (y1 - y0) * t
        draw.line((x0, y, x1, y), fill=255, width=bar)
    return np.asarray(im) > 128


def snowflake_mask(n: int = 720) -> np.ndarray:
    im = Image.new("L", (n, n), 0)
    draw = ImageDraw.Draw(im)
    cx = cy = n / 2
    arm = n * 0.40
    thick = max(8, n // 26)
    branch = max(5, n // 38)
    for i in range(6):
        ang = math.radians(-90 + i * 60)
        tip = (cx + math.cos(ang) * arm, cy + math.sin(ang) * arm)
        draw.line((cx, cy, tip[0], tip[1]), fill=255, width=thick)
        for t, length in ((0.42, 0.18), (0.68, 0.12)):
            bx = cx + math.cos(ang) * arm * t
            by = cy + math.sin(ang) * arm * t
            for side in (-1, 1):
                a2 = ang + side * math.radians(60)
                draw.line(
                    (bx, by, bx + math.cos(a2) * arm * length, by + math.sin(a2) * arm * length),
                    fill=255,
                    width=branch,
                )
    r = n * 0.045
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return np.asarray(im) > 128


def sample_points(mask: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    cols = max(1, int(round(math.sqrt(n * (w / h)))))
    rows = max(1, int(round(n / cols)))
    pts = []
    cw, ch = w / cols, h / rows
    for r in range(rows):
        for c in range(cols):
            x0, x1 = int(c * cw), int((c + 1) * cw)
            y0, y1 = int(r * ch), int((r + 1) * ch)
            block = mask[y0:y1, x0:x1]
            by, bx = np.nonzero(block)
            if len(bx) == 0:
                continue
            k = int(rng.integers(0, len(bx)))
            pts.append((x0 + bx[k] + 0.5, y0 + by[k] + 0.5))
    pts = np.asarray(pts, dtype=np.float64) if pts else np.zeros((0, 2))
    if len(pts) > n:
        pts = pts[rng.choice(len(pts), n, replace=False)]
    elif len(pts) < n:
        need = n - len(pts)
        pick = rng.choice(len(xs), need, replace=True)
        extra = np.column_stack([xs[pick] + 0.5, ys[pick] + 0.5])
        pts = np.vstack([pts, extra]) if len(pts) else extra
    return pts


def place(pts: np.ndarray, center: np.ndarray, span: float) -> np.ndarray:
    lo = pts.min(axis=0)
    hi = pts.max(axis=0)
    size = float((hi - lo).max()) or 1.0
    mid = (lo + hi) / 2
    return (pts - mid) * (span / size) + center


def match_to(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    diff = src[:, None, :] - dst[None, :, :]
    cost = np.einsum("ijk,ijk->ij", diff, diff, optimize=True)
    _, cols = linear_sum_assignment(cost)
    return dst[cols]


def kmeans(points: np.ndarray, k: int, rng: np.random.Generator, iters: int = 16):
    k = min(k, len(points))
    centers = points[rng.choice(len(points), k, replace=False)].copy()
    labels = np.zeros(len(points), dtype=np.int32)
    for _ in range(iters):
        dist = ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = dist.argmin(axis=1)
        for j in range(k):
            chosen = labels == j
            if chosen.any():
                centers[j] = points[chosen].mean(axis=0)
            else:
                centers[j] = points[int(rng.integers(0, len(points)))]
    return labels, centers


def key_times() -> str:
    parts = [f"{t / DUR:.4f}" for t in MARKS]
    parts[-1] = "1"
    return ";".join(parts)


def splines() -> str:
    return ";".join(["0.45 0 0.18 1"] * (len(MARKS) - 1))


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def path_for(tops: np.ndarray, size: float) -> str:
    s = f"{size:.1f}"
    chunks = []
    for x, y in tops:
        chunks.append(f"M{x:.1f} {y:.1f}h{s}v{s}h-{s}z")
    return "".join(chunks)


def build_svg(theme: str, groups: list[np.ndarray], logo_tracks: np.ndarray, pitch: float) -> str:
    pal = THEMES[theme]
    times = key_times()
    ease = splines()
    dot = pitch * 0.72
    radius = pitch * 0.58
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}" role="img" aria-label="Bruno Piter">',
        f'<rect width="{W}" height="{H}" rx="18" fill="{pal["bg"]}"/>',
        f'<rect x="1.5" y="1.5" width="{W - 3}" height="{H - 3}" rx="16.5" fill="none" stroke="{pal["stroke"]}" stroke-width="1.5"/>',
        '<circle cx="28" cy="28" r="6" fill="#FF5F57"/>',
        '<circle cx="48" cy="28" r="6" fill="#FEBC2E"/>',
        '<circle cx="68" cy="28" r="6" fill="#28C840"/>',
        f'<text x="{W / 2:.0f}" y="32" text-anchor="middle" font-size="12" fill="{pal["muted"]}">'
        f'{esc("bruno-piter ~ % ./visual.sh --live")}</text>',
        f'<circle cx="{W - 58}" cy="27" r="3.5" fill="{pal["live"]}">'
        f'<animate attributeName="opacity" values="1;0.3;1" dur="1.6s" repeatCount="indefinite"/></circle>',
        f'<text x="{W - 18}" y="31" text-anchor="end" font-size="11" fill="{pal["live"]}">LIVE</text>',
        f'<rect x="{FRAME["x"]}" y="{FRAME["y"]}" width="{FRAME["w"]}" height="{FRAME["h"]}" rx="12" '
        f'fill="{pal["panel"]}" stroke="{pal["frame"]}"/>',
        f'<text x="{FRAME["x"] + 14}" y="{FRAME["y"] + 20}" font-size="11" letter-spacing="1.5" fill="{pal["cyan"]}">VISUAL.MAP</text>',
        f'<clipPath id="map"><rect x="{AREA["x"]}" y="{AREA["y"]}" width="{AREA["w"]}" height="{AREA["h"]}"/></clipPath>',
        '<g clip-path="url(#map)">',
        f'<g><animate attributeName="opacity" values="1;1;0;0;0;0;0;0;1" keyTimes="{times}" dur="{DUR}s" repeatCount="indefinite"/>',
    ]
    for tops, drift in groups:
        dx, dy = drift
        values = (
            f"0 0;0 0;{dx:.1f} {dy:.1f};{dx:.1f} {dy:.1f};{dx:.1f} {dy:.1f};"
            f"{dx:.1f} {dy:.1f};{dx:.1f} {dy:.1f};{dx:.1f} {dy:.1f};0 0"
        )
        parts.append("<g>")
        parts.append(
            f'<animateTransform attributeName="transform" type="translate" values="{values}" '
            f'keyTimes="{times}" dur="{DUR}s" repeatCount="indefinite" calcMode="spline" keySplines="{ease}"/>'
        )
        parts.append(
            f'<path d="{path_for(tops, dot)}" fill="{pal["violet"]}" shape-rendering="crispEdges"/>'
        )
        parts.append("</g>")
    parts.append("</g>")
    parts.append(
        f'<g><animate attributeName="opacity" values="0;0;1;1;1;1;1;1;0" keyTimes="{times}" '
        f'dur="{DUR}s" repeatCount="indefinite"/>'
    )
    for track in logo_tracks:
        xs = ";".join(f"{p[0]:.1f}" for p in track)
        ys = ";".join(f"{p[1]:.1f}" for p in track)
        parts.append(
            f'<circle r="{radius:.2f}" fill="{pal["violet"]}">'
            f'<animate attributeName="cx" values="{xs}" keyTimes="{times}" dur="{DUR}s" '
            f'repeatCount="indefinite" calcMode="spline" keySplines="{ease}"/>'
            f'<animate attributeName="cy" values="{ys}" keyTimes="{times}" dur="{DUR}s" '
            f'repeatCount="indefinite" calcMode="spline" keySplines="{ease}"/>'
            f"</circle>"
        )
    parts.append("</g></g></svg>")
    return "".join(parts)


def font(size: int):
    for name in ("consola.ttf", "segoeui.ttf", "arial.ttf"):
        path = Path(r"C:\Windows\Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def render_card(theme: str, portrait: np.ndarray | None, logos: np.ndarray | None, pitch: float) -> Image.Image:
    pal = THEMES[theme]
    im = Image.new("RGB", (W, H), pal["bg_rgb"])
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((1, 1, W - 2, H - 2), radius=16, outline=pal["cyan_rgb"], width=2)
    for i, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        cx = 28 + i * 20
        draw.ellipse((cx - 6, 22, cx + 6, 34), fill=color)
    draw.rounded_rectangle(
        (FRAME["x"], FRAME["y"], FRAME["x"] + FRAME["w"], FRAME["y"] + FRAME["h"]),
        radius=12,
        fill=pal["panel_rgb"],
        outline=pal["cyan_rgb"],
    )
    title = font(13)
    draw.text((W / 2, 18), "bruno-piter ~ % ./visual.sh --live", fill=pal["muted"], font=title, anchor="ma")
    draw.text((FRAME["x"] + 14, FRAME["y"] + 8), "VISUAL.MAP", fill=pal["cyan_rgb"], font=font(12))
    if portrait is not None:
        size = pitch * 0.72
        for x, y in portrait:
            draw.rectangle((x, y, x + size, y + size), fill=pal["rgb"])
    if logos is not None:
        r = pitch * 0.58
        for x, y in logos:
            draw.ellipse((x - r, y - r, x + r, y + r), fill=pal["rgb"])
    return im


def save_previews(pitch, portrait_top, react, csharp, snow, crop):
    PREVIEW.mkdir(parents=True, exist_ok=True)
    crop.save(PREVIEW / "crop.jpg", quality=90)
    frames = [
        ("retrato", portrait_top, None),
        ("react", None, react),
        ("csharp", None, csharp),
        ("neve", None, snow),
    ]
    cards = []
    for name, portrait, logos in frames:
        card = render_card("dark", portrait, logos, pitch)
        card.save(PREVIEW / f"{name}.png")
        cards.append(card.resize((280, round(280 * H / W)), Image.Resampling.BOX))
    strip = Image.new("RGB", (280 * 4, cards[0].height), (0, 0, 0))
    for i, card in enumerate(cards):
        strip.paste(card, (i * 280, 0))
    strip.save(PREVIEW / "filmstrip.png")
    print(f"previews em {PREVIEW}")


def main():
    rows = rows_for(COLS)
    print(f"grade {COLS}x{rows}")
    dots, crop, mask = load_portrait(COLS, rows)
    pitch, ox, oy = grid_geometry(COLS, rows)
    subject = int(mask.sum())
    ink = int(dots.sum())
    print(f"sujeito {subject}  pontos {ink}  cobertura {ink / max(subject, 1):.2%}")
    top, centers = dot_points(dots, pitch, ox, oy)

    rng = np.random.default_rng(SEED)
    center = np.array([AREA["x"] + AREA["w"] / 2, AREA["y"] + AREA["h"] / 2])
    span = LOGO_SPAN * min(AREA["w"], AREA["h"])
    react = place(sample_points(ink_png(ICONS / "react.png"), TRAVELLERS, rng), center, span)
    csharp = place(sample_points(csharp_mask(), TRAVELLERS, rng), center, span)
    snow = place(sample_points(snowflake_mask(), TRAVELLERS, rng), center, span)
    csharp = match_to(react, csharp)
    snow = match_to(react, snow)

    # 9 keyframes: escondido no react, segura, vai ao C#, segura, vai ao floco, segura, some
    tracks = np.stack([react, react, react, react, csharp, csharp, snow, snow, snow], axis=1)

    logo_centroid = react.mean(axis=0)
    drift = DRIFT * (logo_centroid - centers)
    drift += rng.normal(0, NOISE, size=drift.shape)
    labels, drift_centers = kmeans(drift, GROUPS, rng)
    groups = []
    for j in range(len(drift_centers)):
        chosen = labels == j
        if not chosen.any():
            continue
        groups.append((top[chosen], drift_centers[j]))
    print(f"grupos {len(groups)}  viajantes {len(react)}")

    save_previews(pitch, top, react, csharp, snow, crop)
    dark = build_svg("dark", groups, tracks, pitch)
    light = build_svg("light", groups, tracks, pitch)
    OUT_DARK.write_text(dark, encoding="utf-8")
    OUT_LIGHT.write_text(light, encoding="utf-8")
    print(f"{OUT_DARK.name} {len(dark) // 1024}KB")
    print(f"{OUT_LIGHT.name} {len(light) // 1024}KB")


if __name__ == "__main__":
    main()
