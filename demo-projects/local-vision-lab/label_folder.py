"""Label images in a folder. Local pixels first, hosted vision only if I opt in."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def route_backend(prefer_local: bool, have_key_name: bool) -> str:
    if prefer_local:
        return "pillow"
    if have_key_name:
        return "openai-vision"
    # Ollama is the offline escape hatch mentioned in the notes.
    return "ollama"


def decide_keep(image: Image.Image) -> str:
    width, height = image.size
    if width < 400 or height < 400:
        return "trash"
    extrema = image.convert("L").getextrema()
    if extrema[1] - extrema[0] < 12:
        return "trash"
    if width * height > 4_000_000:
        return "keep"
    return "maybe"


def main() -> None:
    parser = argparse.ArgumentParser(description="Rough photo labels")
    parser.add_argument("folder")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    backend = route_backend(args.local, False)
    print(f"backend={backend}")
    for path in sorted(Path(args.folder).glob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        with Image.open(path) as image:
            print(f"{path.name}\t{decide_keep(image)}")


if __name__ == "__main__":
    main()
