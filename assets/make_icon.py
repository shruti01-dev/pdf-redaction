from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageChops

INDIGO = (99, 102, 241, 255)
PURPLE = (168, 85, 247, 255)
PAGE = (248, 250, 252, 255)
BAR = (15, 23, 42, 255)


def make_icon(size, shadow=True):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pad = max(1, int(size * (0.06 if shadow else 0.04)))
    radius = max(2, int(size * 0.22))
    box = [pad, pad, size - 1 - pad, size - 1 - pad]

    if shadow and size >= 48:
        s = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(s)
        shift = max(1, int(size * 0.028))
        sdraw.rounded_rectangle(
            [pad + shift, pad + shift, size - 1 - pad + shift, size - 1 - pad + shift],
            radius=radius,
            fill=(21, 32, 51, 72),
        )
        s = s.filter(ImageFilter.GaussianBlur(radius=max(1, int(size * 0.03))))
        img = Image.alpha_composite(img, s)

    fill = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(fill)
    fdraw.rounded_rectangle(box, radius=radius, fill=INDIGO)
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(box, radius=radius, fill=PURPLE)
    fade = Image.new("L", (size, size), 0)
    fade_draw = ImageDraw.Draw(fade)
    fade_draw.rectangle([int(size * 0.45), 0, size, size], fill=255)
    fade = fade.filter(ImageFilter.GaussianBlur(radius=max(1, int(size * 0.12))))
    overlay.putalpha(ImageChops.multiply(overlay.split()[-1], fade))
    fill = Image.alpha_composite(fill, overlay)
    img = Image.alpha_composite(img, fill)
    draw = ImageDraw.Draw(img)

    page_l = int(size * 0.28)
    page_t = int(size * 0.22)
    page_r = int(size * 0.72)
    page_b = int(size * 0.78)
    page_radius = max(1, int(size * 0.04))
    draw.rounded_rectangle(
        [page_l, page_t, page_r, page_b],
        radius=page_radius,
        fill=PAGE,
    )

    bar_h = max(2, int(size * 0.07))
    gap = max(2, int(size * 0.05))
    left = page_l + max(2, int(size * 0.06))
    right = page_r - max(2, int(size * 0.06))
    y = page_t + max(3, int(size * 0.12))
    for i in range(3):
        width_scale = 1.0 if i != 1 else 0.72
        bar_r = left + int((right - left) * width_scale)
        draw.rounded_rectangle(
            [left, y, bar_r, y + bar_h],
            radius=max(1, bar_h // 2),
            fill=BAR if i == 1 else (148, 163, 184, 255),
        )
        y += bar_h + gap

    return img


def main():
    out_dir = Path(__file__).resolve().parent
    master = make_icon(1024, shadow=True)
    master.save(out_dir / "app.png", "PNG")

    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [make_icon(s, shadow=s >= 48) for s in sizes]
    frames[-1].save(
        out_dir / "app.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[:-1],
    )
    print("wrote", out_dir / "app.ico")


if __name__ == "__main__":
    main()
