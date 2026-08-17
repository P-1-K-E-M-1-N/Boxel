#!/usr/bin/env python3
"""Synthetic automotive stress parts: window regulator + car door shell + handle."""
import numpy as np
import trimesh

def window_regulator():
    parts = []
    t = np.linspace(-0.55, 0.55, 40)
    R = 800.0
    path = np.column_stack([R * np.sin(t), 60 * np.cos(3 * t), R * (1 - np.cos(t))])
    path -= path.mean(axis=0)
    for i in range(len(path) - 1):
        parts.append(trimesh.creation.cylinder(radius=9, segment=[path[i], path[i + 1]], sections=12))
    plate = trimesh.creation.box(extents=[110, 14, 90])
    plate.apply_translation(path[22] + [0, 12, 0]); parts.append(plate)
    mot = trimesh.creation.cylinder(radius=32, height=95, sections=32)
    mot.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    mot.apply_translation(path[5] + [-40, -25, -30]); parts.append(mot)
    gbox = trimesh.creation.box(extents=[70, 55, 60])
    gbox.apply_translation(path[5] + [10, -30, -25]); parts.append(gbox)
    drum = trimesh.creation.cylinder(radius=24, height=30, sections=24)
    drum.apply_translation(path[5] + [10, -30, 20]); parts.append(drum)
    for k in (2, 20, 37):
        tab = trimesh.creation.box(extents=[45, 5, 28])
        tab.apply_translation(path[k] + [0, -14, 0]); parts.append(tab)
    return trimesh.util.concatenate(parts)

def car_door_shell():
    m = trimesh.creation.box(extents=[1050, 25, 720])
    m = m.subdivide().subdivide().subdivide()
    v = m.vertices.copy()
    v[:, 1] += 60 * np.cos(v[:, 0] / 1050 * np.pi) * np.cos(v[:, 2] / 720 * np.pi * 0.7)
    m.vertices = v
    cut = trimesh.creation.box(extents=[820, 300, 330])
    cut.apply_translation([0, 0, 195])
    try:
        m = m.difference(cut)
    except BaseException:
        pass
    return m

def door_handle():
    parts = []
    t = np.linspace(0, np.pi, 24)
    pts = np.column_stack([95 * np.cos(t), 18 * np.sin(t), np.zeros_like(t)])
    for i in range(len(pts) - 1):
        parts.append(trimesh.creation.cylinder(radius=13, segment=[pts[i], pts[i + 1]], sections=14))
    for x in (-80, 80):
        st = trimesh.creation.box(extents=[26, 30, 42])
        st.apply_translation([x, 8, -14]); parts.append(st)
    return trimesh.util.concatenate(parts)

if __name__ == "__main__":
    for fn, name in [(window_regulator, "window_regulator"),
                     (car_door_shell, "car_door_shell"),
                     (door_handle, "door_handle")]:
        m = fn(); m.export(f"{name}.stl")
        print(f"{name:18s} extents={np.round(m.extents,1)} tris={len(m.faces)} "
              f"watertight={m.is_watertight}")
