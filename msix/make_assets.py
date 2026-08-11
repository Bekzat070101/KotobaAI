"""KOTOBA·AI — 从 static/logo_icon.png 生成 MSIX 所需 PNG 图标。

输出到 msix/staging/Assets/（StoreLogo 300 / Logo150 150 / Logo44 44）。
"""
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "static", "logo_icon.png")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "staging", "Assets")

SIZES = {
    "StoreLogo.png": 300,
    "Logo150x150.png": 150,
    "Logo44x44.png": 44,
}


def main():
    if not os.path.exists(SRC):
        print("[ERROR] 找不到源图标:", SRC, file=sys.stderr)
        sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    side = min(w, h)
    im = im.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    for name, size in SIZES.items():
        im.resize((size, size), Image.LANCZOS).save(os.path.join(OUT, name))
        print("  asset:", name)
    print("图标生成完成 ->", OUT)


if __name__ == "__main__":
    main()
