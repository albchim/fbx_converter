"""Convert a GLB/GLTF file to FBX using headless Blender (bpy).

FBX cannot carry PBR maps, so next to the FBX we also write:
  <name>_textures/         base color, metallic, roughness, AO, normal images
  <name>_maya_setup.py     run in Maya to build aiStandardSurface materials
"""
import argparse
import pprint
import re
import sys
from pathlib import Path

import bpy

# glTF ORM textures pack channels; map Separate node output names to channel letters.
CHANNELS = {"Red": "R", "Green": "G", "Blue": "B", "R": "R", "G": "G", "B": "B"}


def trace_image(socket):
    """Follow a link upstream to an image texture.

    Returns (image, channel or None) or None if no image is connected.
    """
    channel = None
    while socket is not None and socket.is_linked:
        link = socket.links[0]
        node = link.from_node
        if node.type == "TEX_IMAGE":
            return (node.image, channel) if node.image else None
        if node.type in {"SEPARATE_COLOR", "SEPARATE_RGB"}:
            channel = CHANNELS.get(link.from_socket.name)
            socket = node.inputs[0]
        elif node.type == "NORMAL_MAP":
            socket = node.inputs["Color"]
        else:
            socket = next((i for i in node.inputs if i.is_linked), None)
    return None


def save_image(img, tex_dir: Path, used: dict) -> str:
    if img.name in used:
        return used[img.name]
    tex_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.-]", "_", Path(img.name).stem) + ".png"
    img.filepath_raw = str(tex_dir / name)
    img.file_format = "PNG"
    img.save()
    used[img.name] = f"{tex_dir.name}/{name}"
    return used[img.name]


def extract_materials(tex_dir: Path) -> dict:
    """Save PBR textures to disk and return a description per material."""
    used, result = {}, {}
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        info = {
            "base_color_factor": list(bsdf.inputs["Base Color"].default_value)[:3],
            "metallic_factor": bsdf.inputs["Metallic"].default_value,
            "roughness_factor": bsdf.inputs["Roughness"].default_value,
        }
        maps = {
            "base_color": bsdf.inputs["Base Color"],
            "metallic": bsdf.inputs["Metallic"],
            "roughness": bsdf.inputs["Roughness"],
            "normal": bsdf.inputs["Normal"],
        }
        # glTF importer keeps occlusion in a custom group node
        group = next((n for n in mat.node_tree.nodes
                      if n.type == "GROUP" and "Occlusion" in n.inputs), None)
        if group:
            maps["ao"] = group.inputs["Occlusion"]
        for key, sock in maps.items():
            found = trace_image(sock)
            if found:
                img, channel = found
                info[key] = {"file": save_image(img, tex_dir, used), "channel": channel}
        result[mat.name] = info
        # FBX only sees base color; a metallic factor would render it black in Maya
        bsdf.inputs["Metallic"].default_value = 0.0
    return result


MAYA_SCRIPT = '''"""Run in Maya's Script Editor (Python tab) after importing the FBX."""
import os
import maya.cmds as cmds

MATERIALS = __MATERIALS__
BASE = __BASE__
if "__file__" in globals():
    BASE = os.path.dirname(os.path.abspath(__file__))


def tex(file, colorspace):
    node = cmds.shadingNode("file", asTexture=True, isColorManaged=True)
    cmds.setAttr(node + ".fileTextureName", os.path.join(BASE, file).replace("\\\\", "/"), type="string")
    cmds.setAttr(node + ".colorSpace", colorspace, type="string")
    if colorspace == "Raw":
        cmds.setAttr(node + ".ignoreColorSpaceFileRules", 1)
    return node


def chan(node, c):
    return node + ".outColor" + (c or "R")


for name, m in MATERIALS.items():
    sgs = cmds.listConnections(name, type="shadingEngine") if cmds.objExists(name) else None
    if not sgs:
        print("No shading group found for", name)
        continue
    sg = sgs[0]
    ai = cmds.shadingNode("aiStandardSurface", asShader=True, name=name + "_ai")
    cmds.setAttr(ai + ".base", 1)
    cmds.setAttr(ai + ".specular", 1)
    cmds.setAttr(ai + ".metalness", m["metallic_factor"])
    cmds.setAttr(ai + ".specularRoughness", m["roughness_factor"])
    cmds.setAttr(ai + ".baseColor", *m["base_color_factor"], type="double3")

    if "base_color" in m:
        t = tex(m["base_color"]["file"], "sRGB")
        color_out = t + ".outColor"
        if "ao" in m:
            ao = tex(m["ao"]["file"], "Raw")
            mult = cmds.shadingNode("multiplyDivide", asUtility=True)
            cmds.connectAttr(color_out, mult + ".input1")
            for a in "XYZ":
                cmds.connectAttr(chan(ao, m["ao"]["channel"]), mult + ".input2" + a)
            color_out = mult + ".output"
        cmds.connectAttr(color_out, ai + ".baseColor", force=True)
    if "metallic" in m:
        t = tex(m["metallic"]["file"], "Raw")
        cmds.connectAttr(chan(t, m["metallic"]["channel"]), ai + ".metalness", force=True)
    if "roughness" in m:
        t = tex(m["roughness"]["file"], "Raw")
        cmds.connectAttr(chan(t, m["roughness"]["channel"]), ai + ".specularRoughness", force=True)
    if "normal" in m:
        t = tex(m["normal"]["file"], "Raw")
        n = cmds.shadingNode("aiNormalMap", asUtility=True)
        cmds.connectAttr(t + ".outColor", n + ".input")
        cmds.connectAttr(n + ".outValue", ai + ".normalCamera", force=True)
    cmds.connectAttr(ai + ".outColor", sg + ".surfaceShader", force=True)
    print("Built", ai, "->", sg)
'''


def convert(src: Path, dst: Path) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(src))
    dst.parent.mkdir(parents=True, exist_ok=True)

    tex_dir = dst.parent / f"{dst.stem}_textures"
    materials = extract_materials(tex_dir)
    script = (MAYA_SCRIPT
              .replace("__MATERIALS__", pprint.pformat(materials, sort_dicts=False))
              .replace("__BASE__", repr(str(dst.parent))))
    (dst.parent / f"{dst.stem}_maya_setup.py").write_text(script, encoding="utf-8")

    bpy.ops.export_scene.fbx(
        filepath=str(dst),
        path_mode="COPY",
        embed_textures=False,
        add_leaf_bones=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="input .glb/.gltf file")
    parser.add_argument("output", type=Path, help="output .fbx file path")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1
    dst = args.output.with_suffix(".fbx").resolve()
    convert(args.input, dst)
    if not dst.is_file():
        print("Export failed.", file=sys.stderr)
        return 1
    print(f"Saved {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
