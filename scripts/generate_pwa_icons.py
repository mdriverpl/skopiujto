"""Render the existing document mark at installable PWA sizes."""
from pathlib import Path
from PIL import Image, ImageDraw
root = Path(__file__).resolve().parents[1] / 'public'
for size, filename, maskable in [(192, 'icon-192.png', False), (512, 'icon-512.png', False), (512, 'icon-maskable-512.png', True)]:
    image = Image.new('RGBA', (size * 4, size * 4), '#6654d9' if maskable else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    unit = size * 4 / 192
    def points(values):
        return [(round(x * unit), round(y * unit)) for x, y in values]
    if not maskable:
        draw.rounded_rectangle((0, 0, size * 4 - 1, size * 4 - 1), radius=44 * unit, fill='#6654d9')
    draw.polygon(points([(60, 38), (109, 38), (136, 66), (136, 154), (60, 154)]), fill='white')
    for line in [[(108, 38), (108, 68), (136, 68)], [(77, 91), (120, 91)], [(77, 109), (120, 109)], [(77, 127), (105, 127)]]:
        draw.line(points(line), fill='#6654d9', width=round(8 * unit))
    image.resize((size, size), Image.Resampling.LANCZOS).save(root / filename)
print('Generated 192px, 512px and maskable PWA icons.')
