#!/usr/bin/env python3
"""Complex-part tests: camshaft-like and L-bracket (door hardware proxy).
Checks that concave silhouette packing beats convex-hull packing, and that
results verify clean (no overlaps, inside box)."""
import numpy as np
import trimesh
from shapely.geometry import MultiPoint
from shapely.affinity import rotate as srot, translate as stran
import packcheck as pc

def make_camshaft():
    """300mm shaft D25 with 4 elliptical lobes (55 x 40 x wide 14)."""
    parts = [trimesh.creation.cylinder(radius=12.5, height=300, sections=48)]
    for i, z in enumerate([-105, -35, 35, 105]):
        lobe = trimesh.creation.cylinder(radius=27.5, height=14, sections=48)
        lobe.apply_scale([1.0, 40 / 55, 1.0])
        lobe.apply_translation([6, 0, z])   # lobe offset from axis
        parts.append(lobe)
    m = trimesh.util.concatenate(parts)
    return m

def make_bracket():
    """L-bracket 80 x 60 x 3mm walls, 25mm deep (door-hinge-ish)."""
    a = trimesh.creation.box(extents=[80, 3, 25]); a.apply_translation([40, 1.5, 12.5])
    b = trimesh.creation.box(extents=[3, 60, 25]); b.apply_translation([1.5, 30, 12.5])
    return trimesh.util.concatenate([a, b])

def check(mesh, name, box):
    res = pc.placed_pack(mesh, box, clearance=0.5, angle_step=15)
    best = res[0]
    # hull-only comparison: monkeypatch footprint
    real_fp = pc._footprint
    pc._footprint = lambda m, c: MultiPoint(m.vertices[:, :2]).convex_hull.buffer(c / 2, join_style=2)
    hull_best = pc.placed_pack(mesh, box, clearance=0.5, angle_step=15)[0]
    pc._footprint = real_fp
    # independent overlap/containment verify of the winning layer
    import trimesh as tm
    m = mesh.copy(); m.apply_transform(best["transform"])
    foot = pc._footprint(m, 0.5)
    ang = best["lattice"]["angle"]
    poly = srot(foot, ang, origin="centroid")
    minx, miny, maxx, maxy = poly.bounds
    poly = stran(poly, -(minx + maxx) / 2, -(miny + maxy) / 2)
    from shapely.geometry import box as sbox
    sq = sbox(-1e-4, -1e-4, box[0] + 1e-4, box[1] + 1e-4)
    pflip = srot(poly, 180, origin=(0, 0))
    shp = [stran(pflip if f else poly, x, y) for x, y, f in best["centers"]]
    inside = all(sq.contains(g) for g in shp)
    from scipy.spatial import cKDTree
    c = np.array([(x, y) for x, y, f in best["centers"]]); bad = 0
    if len(c) > 1:
        reach = 2 * max(maxx - minx, maxy - miny)
        for i, j in cKDTree(c).query_pairs(reach):
            if shp[i].intersection(shp[j]).area > 1e-6:
                bad += 1
    gain = 100 * (best["count"] - hull_best["count"]) / max(hull_best["count"], 1)
    print(f"{name:12s} concave={best['count']:>5} ({best['per_layer']}/layer x {best['layers']}, "
          f"{best['lattice']['lattice']}@{best['lattice']['angle']}) | "
          f"hull-only={hull_best['count']:>5} | gain={gain:+.1f}% | "
          f"inside={inside} overlaps={bad}")

if __name__ == "__main__":
    print("box: 600 x 400 x 300 mm (automotive tote)")
    cam = make_camshaft()
    print("camshaft extents:", np.round(cam.extents, 1))
    check(cam, "camshaft", (600, 400, 300))
    br = make_bracket()
    print("bracket extents:", np.round(br.extents, 1))
    check(br, "L-bracket", (600, 400, 300))
