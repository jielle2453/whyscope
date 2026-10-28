"""contact.py <video> <out.png> [n=6] -> n evenly spaced frames side by side (visual check)."""
import subprocess, sys, pathlib, tempfile, re
from PIL import Image
v, out = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
ff = str(pathlib.Path(__file__).resolve().parent.parent / "node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe")
info = subprocess.run([ff, "-hide_banner", "-i", v], capture_output=True, text=True).stderr
m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
ims = []
with tempfile.TemporaryDirectory() as d:
    for i in range(n):
        f = f"{d}/{i}.png"
        subprocess.run([ff, "-loglevel", "error", "-ss", f"{dur * (i + 0.5) / n:.2f}", "-i", v, "-frames:v", "1", "-y", f], check=True)
        im = Image.open(f).convert("RGB"); im.thumbnail((300, 650)); ims.append(im)
W = sum(i.width for i in ims); H = max(i.height for i in ims)
sheet = Image.new("RGB", (W, H)); x = 0
for im in ims: sheet.paste(im, (x, 0)); x += im.width
sheet.save(out); print(dur)
