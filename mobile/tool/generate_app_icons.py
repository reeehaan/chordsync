"""Renders the iOS app icon set from tool/chordsync_icon_square.svg.

iOS rounds the corners itself, so the source is a full square with no rounding
and no transparency. Needs `rsvg-convert` (brew install librsvg).

    python3 tool/generate_app_icons.py
"""

import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root / "tool" / "chordsync_icon_square.svg"
icons = root / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"

contents = json.loads((icons / "Contents.json").read_text())
for image in contents["images"]:
    points = float(image["size"].split("x")[0])
    pixels = round(points * int(image["scale"].rstrip("x")))
    subprocess.run(
        [
            "rsvg-convert",
            "-w", str(pixels),
            "-h", str(pixels),
            str(source),
            "-o", str(icons / image["filename"]),
        ],
        check=True,
    )
    print(f'{image["filename"]}: {pixels}px')
