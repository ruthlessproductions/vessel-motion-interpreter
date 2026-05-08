"""
Vessel — Blender batch render script
-------------------------------------
1. Download your Mixamo animations as FBX (with skin), one per motion ID.
   Rename each file to match the motion ID exactly, e.g. idle_sway.fbx
2. Put all FBX files in FBX_DIR.
3. Open Blender, go to Scripting tab, paste this file, hit Run Script.
4. Renders each clip to OUTPUT_DIR/<motion_id>.mp4

Adjust FBX_DIR and OUTPUT_DIR before running.
"""

import bpy
import math
import os
from pathlib import Path

# ── Configure these two paths ──────────────────────────────────────────────
REPO_DIR   = Path.home() / "Documents" / "GitHub" / "vessel-motion-interpreter"
FBX_DIR    = REPO_DIR / "clips"   # drop FBX files here; MP4s render alongside them
OUTPUT_DIR = REPO_DIR / "clips"

# ── Render settings ────────────────────────────────────────────────────────
RESOLUTION_X  = 1080
RESOLUTION_Y  = 1440   # 3:4 portrait
FRAME_RATE    = 24
HOLD_FRAMES   = 12     # extra still frames appended at end for clean loop-out

# ── All valid motion IDs ───────────────────────────────────────────────────
MOTION_IDS = {
    'contemplate_slow_turn','idle_sway','nod_slow','nod_sharp','look_up_think',
    'lean_in_interest','lean_back_assess','tilt_head_curious','step_forward_engage',
    'step_back_consider','open_chest_warmth','arms_cross_skeptic','subtle_weight_shift',
    'sharp_emphasis_gesture','spread_hands_open','finger_tap_think','look_away_process',
    'stillness_hold','small_head_shake','soft_exhale_settle'
}

# ── Mixamo filename → motion ID map ───────────────────────────────────────
# Key   = the filename you downloaded from Mixamo (without .fbx)
# Value = the motion_id the app expects
MOTION_MAP = {
    "Breathing Idle":                 "idle_sway",
    "Standing Idle":                  "stillness_hold",
    "Thinking":                       "contemplate_slow_turn",
    "Head Nod Yes":                   "nod_slow",
    "Fast Head Nod":                  "nod_sharp",
    "Looking Up":                     "look_up_think",
    "Leaning Forward Idle":           "lean_in_interest",
    "Leaning Back Idle":              "lean_back_assess",
    "Head Tilt":                      "tilt_head_curious",
    "Step Forward":                   "step_forward_engage",
    "Step Back":                      "step_back_consider",
    "Open Arms":                      "open_chest_warmth",
    "Arms Crossed Idle":              "arms_cross_skeptic",
    "Weight Shift":                   "subtle_weight_shift",
    "Pointing Gesture":               "sharp_emphasis_gesture",
    "Hands Spread":                   "spread_hands_open",
    "Chin Scratch":                   "finger_tap_think",
    "Looking Away":                   "look_away_process",
    "Head Shake No":                  "small_head_shake",
    "Exhale":                         "soft_exhale_settle",
}

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes) + list(bpy.data.armatures) + list(bpy.data.actions):
        block.user_clear()
        try:
            bpy.data.batch_remove([block])
        except Exception:
            pass


def setup_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background") or world.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.018, 0.018, 0.014, 1.0)  # warm dark
    bg.inputs[1].default_value = 1.0


def setup_camera():
    bpy.ops.object.camera_add(
        location=(0.0, -2.6, 1.35),
        rotation=(math.radians(78), 0.0, 0.0)
    )
    cam = bpy.context.active_object
    cam.name = "VesselCam"
    cam.data.lens = 85          # 85mm — flattering, no distortion
    cam.data.clip_start = 0.1
    bpy.context.scene.camera = cam
    return cam


def setup_lights():
    # Key — soft area light, front left
    bpy.ops.object.light_add(type='AREA', location=(-1.4, -1.8, 2.8))
    key = bpy.context.active_object
    key.name = "KeyLight"
    key.data.energy = 450
    key.data.size = 1.8
    key.rotation_euler = (math.radians(55), math.radians(-18), math.radians(-30))

    # Fill — dimmer, front right
    bpy.ops.object.light_add(type='AREA', location=(1.6, -1.8, 2.2))
    fill = bpy.context.active_object
    fill.name = "FillLight"
    fill.data.energy = 90
    fill.data.size = 2.2
    fill.rotation_euler = (math.radians(55), math.radians(18), math.radians(30))

    # Rim — behind character, subtle edge separation
    bpy.ops.object.light_add(type='AREA', location=(0.0, 1.8, 2.6))
    rim = bpy.context.active_object
    rim.name = "RimLight"
    rim.data.energy = 70
    rim.data.size = 1.2
    rim.rotation_euler = (math.radians(130), 0.0, 0.0)


def setup_render(output_path: Path):
    scene = bpy.context.scene
    render = scene.render

    render.engine = 'CYCLES'
    scene.cycles.samples = 64          # fast enough for character clips
    scene.cycles.use_denoising = True

    render.resolution_x = RESOLUTION_X
    render.resolution_y = RESOLUTION_Y
    render.fps = FRAME_RATE
    render.film_transparent = False

    render.image_settings.file_format = 'FFMPEG'
    render.ffmpeg.format = 'MPEG4'
    render.ffmpeg.codec = 'H264'
    render.ffmpeg.constant_rate_factor = 'MEDIUM'
    render.ffmpeg.audio_codec = 'NONE'

    render.filepath = str(output_path)


def import_fbx(fbx_path: Path):
    bpy.ops.import_scene.fbx(
        filepath=str(fbx_path),
        use_anim=True,
        ignore_leaf_bones=True,
        force_connect_children=False,
        automatic_bone_orientation=True,
    )
    # Return the armature
    for obj in bpy.context.selected_objects:
        if obj.type == 'ARMATURE':
            return obj
    return None


def get_action_range(armature):
    """Return (start, end) frame of the active action."""
    if armature and armature.animation_data and armature.animation_data.action:
        action = armature.animation_data.action
        frames = [kp.co.x for fc in action.fcurves for kp in fc.keyframe_points]
        if frames:
            return int(min(frames)), int(max(frames))
    return bpy.context.scene.frame_start, bpy.context.scene.frame_end


def center_character(armature):
    """Move character so hips sit at world origin."""
    if not armature:
        return
    bpy.context.view_layer.update()
    armature.location = (0.0, 0.0, 0.0)


def render_clip(fbx_path: Path, motion_id: str):
    print(f"\n── Rendering: {motion_id} ──")

    # Remove previous character (keep lights + camera)
    keep = {"VesselCam", "KeyLight", "FillLight", "RimLight"}
    for obj in [o for o in bpy.data.objects if o.name not in keep]:
        bpy.data.objects.remove(obj, do_unlink=True)

    armature = import_fbx(fbx_path)
    center_character(armature)

    start, end = get_action_range(armature)
    scene = bpy.context.scene
    scene.frame_start = start
    scene.frame_end = end + HOLD_FRAMES   # hold last pose briefly

    output = OUTPUT_DIR / f"{motion_id}.mp4"
    setup_render(output)

    bpy.ops.render.render(animation=True, write_still=False)
    print(f"   → saved: {output}")


def run():
    print("\n════ Vessel render batch ════")

    clear_scene()
    setup_world()
    setup_camera()
    setup_lights()

    fbx_files = list(FBX_DIR.glob("*.fbx"))
    if not fbx_files:
        print(f"No FBX files found in {FBX_DIR}")
        return

    rendered, skipped = 0, 0
    for fbx_path in sorted(fbx_files):
        stem = fbx_path.stem
        # Use filename directly if it matches a motion ID, otherwise check MOTION_MAP
        if stem in MOTION_IDS:
            motion_id = stem
        else:
            motion_id = MOTION_MAP.get(stem)
        if not motion_id:
            print(f"Skipping {stem} — no matching motion ID")
            skipped += 1
            continue
        render_clip(fbx_path, motion_id)
        rendered += 1

    print(f"\n════ Done: {rendered} rendered, {skipped} skipped ════")
    print(f"Clips saved to: {OUTPUT_DIR}")


run()
