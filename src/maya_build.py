"""Stage 2 (run with mayapy): build a portable Maya project from the staged FBX + textures.

Usage: mayapy maya_build.py <stage_dir> <project_dir>
"""
import json
import re
import shutil
import sys
from pathlib import Path

import maya.cmds as cmds
import maya.standalone

DEFAULT_SHADERS = {"lambert1", "particleCloud1", "standardSurface1"}
PLACE2D_ATTRS = [
    "coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger",
    "wrapU", "wrapV", "repeatUV", "offset", "rotateUV", "noiseUV",
    "vertexUvOne", "vertexUvTwo", "vertexUvThree", "vertexCameraOne",
]


def make_project(project: Path) -> None:
    for sub in ("scenes", "sourceimages", "assets"):
        (project / sub).mkdir(parents=True, exist_ok=True)
    cmds.workspace(str(project), newWorkspace=True)
    cmds.workspace(str(project), openWorkspace=True)
    cmds.workspace(fileRule=["scene", "scenes"])
    cmds.workspace(fileRule=["sourceImages", "sourceimages"])
    cmds.workspace(fileRule=["fbx", "assets"])
    cmds.workspace(saveWorkspace=True)


def file_node(rel_path: str, colorspace: str, name: str) -> str:
    """Create a file texture node (with place2dTexture) using a project-relative path."""
    node = cmds.shadingNode("file", asTexture=True, name=name, isColorManaged=True)
    place = cmds.shadingNode("place2dTexture", asUtility=True)
    cmds.connectAttr(place + ".outUV", node + ".uvCoord")
    cmds.connectAttr(place + ".outUvFilterSize", node + ".uvFilterSize")
    for attr in PLACE2D_ATTRS:
        cmds.connectAttr(f"{place}.{attr}", f"{node}.{attr}")
    cmds.setAttr(node + ".fileTextureName", rel_path, type="string")
    cmds.setAttr(node + ".colorSpace", colorspace, type="string")
    if colorspace == "Raw":
        cmds.setAttr(node + ".ignoreColorSpaceFileRules", 1)
    return node


def out(node: str, channel) -> str:
    return f"{node}.outColor{channel or 'R'}"


def find_shading_group(mat_name: str):
    """Find the imported shader for a Blender material name and return (shader, sg)."""
    wanted = mat_name.replace(".", "_")
    for shader in cmds.ls(materials=True):
        if shader in DEFAULT_SHADERS:
            continue
        if shader.split(":")[-1] in (mat_name, wanted):
            sgs = cmds.listConnections(shader, type="shadingEngine") or []
            if sgs:
                return shader, sgs[0]
    return None, None


def build_material(name: str, m: dict, old_shader: str, sg: str, report: list) -> None:
    ss = cmds.shadingNode("standardSurface", asShader=True, name=f"{name}_mat")
    cmds.setAttr(ss + ".base", 1)
    cmds.setAttr(ss + ".baseColor", *m["base_color_factor"], type="double3")
    cmds.setAttr(ss + ".metalness", m["metallic_factor"])
    cmds.setAttr(ss + ".specularRoughness", m["roughness_factor"])

    def tex(key, colorspace):
        return file_node(f"sourceimages/{m[key]['file']}", colorspace, f"{name}_{key}_file")

    if "base_color" in m:
        cmds.connectAttr(tex("base_color", "sRGB") + ".outColor", ss + ".baseColor", force=True)
    if "metallic" in m:
        node = tex("metallic", "Raw")
        cmds.connectAttr(out(node, m["metallic"]["channel"]), ss + ".metalness", force=True)
    if "roughness" in m:
        node = tex("roughness", "Raw")
        cmds.connectAttr(out(node, m["roughness"]["channel"]), ss + ".specularRoughness", force=True)
    if "normal" in m:
        node = tex("normal", "Raw")
        bump = cmds.shadingNode("bump2d", asUtility=True, name=f"{name}_bump")
        cmds.setAttr(bump + ".bumpInterp", 1)  # tangent-space normal map
        cmds.setAttr(bump + ".bumpDepth", 0.0)  # normal map wired up but disabled
        cmds.connectAttr(node + ".outAlpha", bump + ".bumpValue")
        cmds.connectAttr(bump + ".outNormal", ss + ".normalCamera", force=True)
    if "ao" in m:
        # standardSurface has no AO slot; keep the map in the scene, unconnected
        tex("ao", "Raw")
        report.append(f"{name}: AO map kept as unconnected file node (no AO slot)")

    cmds.connectAttr(ss + ".outColor", sg + ".surfaceShader", force=True)
    # drop the FBX-imported shader together with its texture/bump network
    stale = [n for n in cmds.listHistory(old_shader) or [] if n != sg and cmds.objExists(n)]
    cmds.delete(stale)
    report.append(f"{name}: built {ss}")


def make_paths_relative(scene: Path, project: Path) -> None:
    """Maya resolves texture paths to absolute on set; rewrite them as project-relative."""
    prefix = re.escape(project.as_posix()) + r"/+sourceimages/"
    text = scene.read_text(encoding="utf-8")
    scene.write_text(re.sub(prefix, "sourceimages/", text), encoding="utf-8")


def main(stage: Path, project: Path) -> int:
    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    name = manifest["name"]
    report = []

    maya.standalone.initialize(name="python")
    try:
        cmds.loadPlugin("fbxmaya", quiet=True)
        make_project(project)

        shutil.copytree(stage / "textures", project / "sourceimages", dirs_exist_ok=True) \
            if (stage / "textures").is_dir() else None
        fbx = project / "assets" / manifest["fbx"]
        shutil.copy2(stage / manifest["fbx"], fbx)

        cmds.file(new=True, force=True)
        cmds.file(str(fbx), i=True, type="FBX", ignoreVersion=True,
                  mergeNamespacesOnClash=False, options="fbx", pr=True)

        for mat_name, m in manifest["materials"].items():
            shader, sg = find_shading_group(mat_name)
            if not shader:
                report.append(f"{mat_name}: no imported shader found, skipped")
                continue
            build_material(mat_name.replace(".", "_"), m, shader, sg, report)

        cmds.file(rename=str(project / "scenes" / f"{name}.ma"))
        scene = project / "scenes" / f"{name}.ma"
        cmds.file(save=True, type="mayaAscii")
        make_paths_relative(scene, project)
    finally:
        maya.standalone.uninitialize()

    print("\n".join(report))
    print(f"Project: {project}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
