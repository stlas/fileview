"""Builds the FileView icon set from the SVG sources. Usage: python3 build_icons.py icons  (needs cairosvg + Pillow)."""
import io, sys
import cairosvg
from PIL import Image

d = sys.argv[1]
q = {n: open(f"{d}/{n}.svg", "rb").read() for n in ("fileview", "fileview-16", "fileview-maskable")}


def png(name, px):
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=q[name], output_width=px, output_height=px))).convert("RGBA")


ziele = {
    "favicon-16.png": ("fileview-16", 16),
    "favicon-32.png": ("fileview", 32),
    "icon-192.png": ("fileview", 192),
    "icon-512.png": ("fileview", 512),
    "icon-maskable-512.png": ("fileview-maskable", 512),
    "apple-touch-icon.png": ("fileview-maskable", 180),
}
for datei, (quelle, px) in ziele.items():
    png(quelle, px).save(f"{d}/{datei}", optimize=True)

# favicon.ico with 16 (pixel-tuned variant), 32 and 48
ico16, ico32, ico48 = png("fileview-16", 16), png("fileview", 32), png("fileview", 48)
ico48.save(f"{d}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[ico16, ico32])
print("built:", ", ".join(list(ziele) + ["favicon.ico"]))
