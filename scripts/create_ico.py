"""Create a multi-size .ico file from a source PNG image.

Usage:
    python scripts/create_ico.py [source.png]

If no argument is given, defaults to assets/icon.png.
Outputs the .ico file to assets/slaktbusken.ico.

Requires Pillow: pip install Pillow
"""

import sys
from pathlib import Path

from PIL import Image

SIZES = [256, 128, 64, 48, 32, 24, 16]

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_SOURCE = ASSETS_DIR / "icon.png"
OUTPUT_PATH = ASSETS_DIR / "slaktbusken.ico"


def create_ico(source_path: Path) -> None:
    """Resize source PNG to multiple sizes and save as .ico."""
    if not source_path.exists():
        print(f"Error: Source file not found: {source_path}")
        sys.exit(1)

    img = Image.open(source_path)

    # Ensure RGBA for transparency support
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Create resized versions using high-quality downsampling
    resized = [img.resize((size, size), Image.LANCZOS) for size in SIZES]

    # Save as .ico with all sizes embedded
    resized[0].save(
        OUTPUT_PATH,
        format="ICO",
        sizes=[(size, size) for size in SIZES],
        append_images=resized[1:],
    )

    print(f"Created {OUTPUT_PATH} with sizes: {', '.join(f'{s}x{s}' for s in SIZES)}")


if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    ASSETS_DIR.mkdir(exist_ok=True)
    create_ico(source)
