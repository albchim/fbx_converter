"""Stage 1 (headless Blender): GLB -> FBX + separate PBR textures + manifest.json."""
import json
import re
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
    """Save an image as PNG into tex_dir; returns the file name."""
    if img.name in used:
        return used[img.name]
    tex_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.-]", "_", Path(img.name).stem) + ".png"
    img.filepath_raw = str(tex_dir / name)
    img.file_format = "PNG"
    img.save()
    used[img.name] = name
    return name


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
    return result


def run(src: Path, stage_dir: Path, name: str) -> Path:
    """Convert src into stage_dir; returns the manifest path."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(src))
    stage_dir.mkdir(parents=True, exist_ok=True)

    materials = extract_materials(stage_dir / "textures")
    fbx = stage_dir / f"{name}.fbx"
    bpy.ops.export_scene.fbx(
        filepath=str(fbx),
        path_mode="STRIP",
        add_leaf_bones=False,
    )
    manifest = stage_dir / "manifest.json"
    manifest.write_text(
        json.dumps({"name": name, "fbx": fbx.name, "materials": materials}, indent=2),
        encoding="utf-8",
    )
    return manifest
