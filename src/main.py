"""Convert a GLB/GLTF file into a portable Maya project.

1. Headless Blender (bpy) converts GLB -> FBX and extracts PBR textures.
2. The newest installed Maya's mayapy imports the FBX, builds standardSurface
   materials with project-relative texture paths and saves a .ma scene.

Project layout: <output dir>/<name>/{workspace.mel, scenes/, sourceimages/, assets/}
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
MAYA_ROOT = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Autodesk"


def find_mayapy(override: str | None) -> Path | None:
    """Return mayapy.exe of the highest installed Maya version (or of `override`)."""
    candidates = []
    if override:
        candidates.append((0, Path(override)))
    elif os.environ.get("MAYA_LOCATION"):
        candidates.append((0, Path(os.environ["MAYA_LOCATION"])))
    if not candidates and MAYA_ROOT.is_dir():
        for d in MAYA_ROOT.iterdir():
            m = re.fullmatch(r"Maya(\d{4})", d.name)
            if m:
                candidates.append((int(m.group(1)), d))
    for _, d in sorted(candidates, key=lambda c: c[0], reverse=True):
        exe = d / "bin" / "mayapy.exe"
        if exe.is_file():
            return exe
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="input .glb/.gltf file")
    parser.add_argument("output", type=Path,
                        help="output path; its stem names the project, created next to it")
    parser.add_argument("--maya", help="Maya install dir (default: newest found)")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1
    mayapy = find_mayapy(args.maya)
    if mayapy is None:
        print("No Maya installation found (use --maya or MAYA_LOCATION).", file=sys.stderr)
        return 1
    print(f"Using {mayapy}")

    name = re.sub(r"[^\w-]", "_", args.output.stem)
    project = args.output.resolve().parent / name

    import blender_stage  # imports bpy, so only load it when needed

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        blender_stage.run(args.input.resolve(), stage, name)
        result = subprocess.run(
            [str(mayapy), str(HERE / "maya_build.py"), str(stage), str(project)]
        )
    scene = project / "scenes" / f"{name}.ma"
    if result.returncode != 0 or not scene.is_file():
        print("Maya build failed.", file=sys.stderr)
        return 1
    print(f"Saved {scene}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
