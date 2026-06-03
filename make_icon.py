"""Generate icon.ico (and icon.png) — a radar-scope app icon."""
import math
from PIL import Image, ImageDraw

def render(size: int) -> Image.Image:
    # supersample for smooth edges
    S = size * 4
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = S / 2
    R = S * 0.47

    # rounded-square dark background
    pad = S * 0.02
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.22,
                        fill=(8, 14, 26, 255))

    # outer glow ring
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(0, 180, 255, 90), width=int(S * 0.012))

    # concentric range rings
    for frac in (0.34, 0.66, 1.0):
        rr = R * 0.9 * frac
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                  outline=(0, 200, 255, 130), width=max(1, int(S * 0.006)))

    # crosshairs
    d.line([cx, cy - R * 0.9, cx, cy + R * 0.9], fill=(0, 200, 255, 70), width=max(1, int(S * 0.005)))
    d.line([cx - R * 0.9, cy, cx + R * 0.9, cy], fill=(0, 200, 255, 70), width=max(1, int(S * 0.005)))

    # radar sweep wedge (fading green)
    sweep_start = -60
    steps = 60
    for i in range(steps):
        a0 = sweep_start - i * 1.4
        a1 = a0 - 1.6
        alpha = int(150 * (1 - i / steps))
        rr = R * 0.9
        d.pieslice([cx - rr, cy - rr, cx + rr, cy + rr], a1, a0,
                   fill=(0, 230, 120, alpha))

    # leading sweep line (bright)
    ang = math.radians(sweep_start)
    d.line([cx, cy, cx + R * 0.9 * math.cos(ang), cy + R * 0.9 * math.sin(ang)],
           fill=(120, 255, 170, 255), width=max(1, int(S * 0.012)))

    # a couple of "echo" blips
    for (bx, by, br, col) in [(0.28, -0.15, 0.07, (255, 210, 0)),
                              (0.40, 0.10, 0.05, (255, 80, 60)),
                              (-0.25, 0.30, 0.05, (0, 230, 120))]:
        ex, ey = cx + R * bx, cy + R * by
        er = R * br
        d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=col + (235,))

    # center dot
    cr = S * 0.03
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(255, 255, 255, 255))

    return img.resize((size, size), Image.LANCZOS)


sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [render(s) for s in sizes]
imgs[-1].save('icon.png')
imgs[-1].save('icon.ico', format='ICO', sizes=[(s, s) for s in sizes])
print('Wrote icon.ico and icon.png')
