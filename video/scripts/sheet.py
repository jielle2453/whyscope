import sys, pathlib
from PIL import Image
d = pathlib.Path(__file__).resolve().parent.parent / ".tmp/stills"
fr = sys.argv[2:]; cols = int(sys.argv[1])
ims = [Image.open(d / f"f{f}.jpg") for f in fr]
w, h = ims[0].size; w2, h2 = w // 2, h // 2
rows = (len(ims) + cols - 1) // cols
S = Image.new("RGB", (w2 * cols, h2 * rows), "white")
for i, im in enumerate(ims): S.paste(im.resize((w2, h2)), ((i % cols) * w2, (i // cols) * h2))
S.save(d / "sheet.jpg", quality=85)
