#!/usr/bin/env python3
"""
PackCheck — how many parts fit in a box, and how should they sit?

Pipeline:
  1. Load a CAD file (.stp/.step via cascadio, or .stl/.obj/.glb directly).
  2. Find the part's gravity-stable resting orientations (trimesh stable poses).
  3. For each orientation, project the part's convex footprint and search
     2D lattices (rectangular + offset/honeycomb, over footprint rotations)
     that fit inside the box footprint. Stack layers to the box height.
  4. Report PLACED count (arranged packing, with clearance) and POURED
     estimate (random fill, calibrated against packing physics literature).

Usage:
  python packcheck.py part.stp --box 228.6 228.6 228.6 --clearance 0.2
  python packcheck.py part.stp --box-inches 9 9 9 --html out.html
"""
import argparse, json, sys
import numpy as np
import trimesh
from shapely.geometry import MultiPoint, box as shapely_box
from shapely.affinity import translate, rotate

# ---------------------------------------------------------------- loading

def load_mesh(path, linear_tol=0.05):
    """Load CAD file -> trimesh (mm). STEP goes through cascadio (mm->m->mm)."""
    p = str(path)
    if p.lower().endswith((".stp", ".step")):
        import cascadio, tempfile, os
        tmp = tempfile.mktemp(suffix=".glb")
        cascadio.step_to_glb(p, tmp, tol_linear=linear_tol)
        m = trimesh.load(tmp, force="mesh")
        os.unlink(tmp)
        m.apply_scale(1000.0)          # glb is meters; work in mm
    else:
        m = trimesh.load(p, force="mesh")
    if not m.is_watertight:
        m.merge_vertices()
        trimesh.repair.fill_holes(m)
    return m

# ------------------------------------------------------- orientations

def resting_orientations(mesh, max_poses=4):
    """Gravity-stable poses, most probable first. Returns list of 4x4 transforms."""
    try:
        transforms, probs = trimesh.poses.compute_stable_poses(mesh, n_samples=1)
        order = np.argsort(probs)[::-1]
        return [transforms[i] for i in order[:max_poses]], [float(probs[i]) for i in order[:max_poses]]
    except BaseException:
        # fallback: rest on each principal axis-aligned face of the OBB
        T = mesh.bounding_box_oriented.primitive.transform
        out = []
        for ax in range(3):
            for flip in (0, 1):
                R = trimesh.geometry.align_vectors(
                    T[:3, ax] * (1 if flip == 0 else -1), [0, 0, -1])
                out.append(R)
        return out[:max_poses], [1.0 / max_poses] * max_poses

# ------------------------------------------------------- footprints

def _footprint(oriented_mesh, clearance):
    """2D outline of the part seen from above, grown by clearance/2.

    Uses the TRUE projected silhouette when possible (so concave parts —
    camshafts, brackets, latches — can interlock row-to-row), falling back
    to the convex hull. Through-holes are filled: another copy of the same
    part can't live inside them anyway."""
    from shapely.geometry import Polygon
    try:
        outline = trimesh.path.polygons.projected(
            oriented_mesh, normal=[0, 0, 1], ignore_sign=True)
        if outline.geom_type == "MultiPolygon":
            outline = max(outline.geoms, key=lambda g: g.area) \
                if len(outline.geoms) == 1 else None
        if outline is not None:
            poly = Polygon(outline.exterior)          # fill holes
            poly = poly.simplify(0.05).buffer(clearance / 2.0, join_style=2)
            if poly.geom_type == "Polygon" and poly.area > 0:
                return poly
    except BaseException:
        pass
    return MultiPoint(oriented_mesh.vertices[:, :2]).convex_hull.buffer(
        clearance / 2.0, join_style=2)

# ------------------------------------------------------- containers
# Inside dimensions from published packaging specs (mm). Weight limits are
# typical gross-load ratings — override with --weight-limit when you know
# the real spec for your box.
GAL = 3.785412e6  # mm^3

CONTAINERS = {
    # 55-gal open-head steel drum: ~22.5" ID x 33" inside height
    "drum55":  {"type": "cylinder", "diameter": 571.5, "height": 838.2,
                "weight_limit_kg": 400.0},
    # 5-gal plastic pail: tapers ~10.33" bottom ID -> ~11.9" top ID, 13.4" deep
    "pail5":   {"type": "frustum", "bottom_diameter": 262.4,
                "top_diameter": 302.3, "height": 340.4, "weight_limit_kg": 34.0},
    # Gaylord bulk box on 48x40 pallet, ~46.5 x 38.5 x 35 inside
    "gaylord": {"type": "box", "w": 1181.1, "d": 977.9, "h": 889.0,
                "weight_limit_kg": 680.0},
}
# Corrugated box gross-weight ratings (lbs -> kg)
ECT_LIMIT_KG = {32: 29.5, 44: 43.1, 48: 54.4, 51: 63.5}

def _container_volume(c):
    if c["type"] == "box":
        return c["w"] * c["d"] * c["h"]
    if c["type"] == "cylinder":
        return np.pi * (c["diameter"] / 2) ** 2 * c["height"]
    if c["type"] == "frustum":
        R, r, h = c["top_diameter"] / 2, c["bottom_diameter"] / 2, c["height"]
        return np.pi * h / 3 * (R * R + R * r + r * r)
    raise ValueError(c["type"])

def _circle(r, n=96):
    from shapely.geometry import Polygon
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return Polygon(np.column_stack([r * np.cos(a), r * np.sin(a)]))

def _container_region(c, z_lo, z_hi):
    """Conservative horizontal cross-section over the height band [z_lo, z_hi]:
    the narrowest section in the band, so every layer fits for sure."""
    if c["type"] == "box":
        return shapely_box(0, 0, c["w"], c["d"])
    if c["type"] == "cylinder":
        return _circle(c["diameter"] / 2)
    if c["type"] == "frustum":
        r0, r1, h = c["bottom_diameter"] / 2, c["top_diameter"] / 2, c["height"]
        rad = lambda z: r0 + (r1 - r0) * max(0.0, min(1.0, z / h))
        return _circle(min(rad(z_lo), rad(z_hi)))
    raise ValueError(c["type"])

def apply_packaging(c, packaging):
    """Shrink the container by liner thickness; return (container, packaging)."""
    if not packaging:
        return c, {}
    p = dict(packaging)
    t = float(p.get("liner_mm", 0.0))
    if t > 0:
        c = dict(c)
        if c["type"] == "box":
            c["w"] -= 2 * t; c["d"] -= 2 * t; c["h"] -= 2 * t
        elif c["type"] == "cylinder":
            c["diameter"] -= 2 * t; c["height"] -= 2 * t
        elif c["type"] == "frustum":
            c["top_diameter"] -= 2 * t; c["bottom_diameter"] -= 2 * t
            c["height"] -= 2 * t
    return c, p

# ------------------------------------------------------- lattice packing

def _separated(a, b):
    """True if shapes a and b have real separation (no overlap, no contact)."""
    return a.intersection(b).area < 1e-9 and a.distance(b) > 0

def _verify_no_overlap(poly, placements, reach, poly_flip=None):
    """Hard check: no two placements overlap. placements = [(x, y, flip)].
    Returns True if clean."""
    if len(placements) < 2:
        return True
    from scipy.spatial import cKDTree
    c = np.asarray([(p[0], p[1]) for p in placements])
    shapes = [translate(poly_flip if p[2] else poly, p[0], p[1])
              for p in placements] if poly_flip is not None else None
    for i, j in cKDTree(c).query_pairs(reach):
        a = shapes[i] if shapes else translate(poly, *c[i])
        b = shapes[j] if shapes else translate(poly, *c[j])
        if a.intersection(b).area > 1e-3:   # ignore sub-micron slivers
            return False
    return True

def _edge_angles(poly, max_angles=24):
    """Angles (deg, mod 180) that align the footprint's longest edges with x.
    Lattice optima almost always sit at edge-aligned rotations."""
    xy = np.asarray(poly.exterior.coords)
    d = np.diff(xy, axis=0)
    lengths = np.hypot(d[:, 0], d[:, 1])
    angs = np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 180.0
    order = np.argsort(lengths)[::-1]
    out = []
    for i in order:
        a = -angs[i] % 180.0          # rotation that lays this edge along x
        for cand in (a, (a + 90.0) % 180.0):   # ...and along y (row direction)
            if all(min(abs(cand - b), 180 - abs(cand - b)) > 0.5 for b in out):
                out.append(round(cand, 2))
        if len(out) >= max_angles:
            break
    return out

def pack_layer(footprint, region, angle_step=15.0, offset_step=None,
               restrict=None):
    """Best 2D lattice of `footprint` inside `region` (any shapely polygon:
    rectangle for boxes, circle for drums/pails). Returns (count, centers, meta).
    `restrict` = meta from a previous solve: reuse angle/lattice, rescan offsets."""
    from shapely.prepared import prep
    if isinstance(region, (tuple, list)):          # back-compat: (w, d)
        region = shapely_box(0, 0, region[0], region[1])
    eps = 1e-6
    square = prep(region.buffer(eps))
    rminx, rminy, rmaxx, rmaxy = region.bounds
    box_w, box_d = rmaxx - rminx, rmaxy - rminy
    best = (0, [], None)
    if restrict is not None:
        angles = [restrict["angle"]]
    else:
        angles = sorted(set(list(np.arange(0, 180, angle_step)) + _edge_angles(footprint)))
    for ang in angles:
        poly = rotate(footprint, ang, origin="centroid")
        minx, miny, maxx, maxy = poly.bounds
        w, h = maxx - minx, maxy - miny
        if w > box_w + 1e-9 or h > box_d + 1e-9:
            continue
        poly = translate(poly, -(minx + maxx) / 2, -(miny + maxy) / 2)  # center at origin
        flip = rotate(poly, 180, origin=(0, 0))    # part turned around, same bbox
        symmetric = poly.symmetric_difference(flip).area < 1e-6

        def gap_search(off, other):
            """Min row pitch when the adjacent row holds `other` at x-offset off."""
            def ok(dy):
                for dx in (off, off - w):
                    if not _separated(poly, translate(other, dx, dy)):
                        return False
                return _separated(poly, translate(poly, 0.0, 2 * dy))
            if not ok(h):
                return None
            lo, hi = h * 0.25, h
            while hi - lo > 0.02:
                mid = 0.5 * (lo + hi)
                if ok(mid):
                    hi = mid
                else:
                    lo = mid
            return hi

        # candidate lattices: grid, staggered, nested — plus versions where
        # alternate rows are flipped 180° so concave parts interleave
        if restrict is not None:
            px_r, py_r = restrict["pitch"]
            cands = [(restrict["lattice"], px_r, py_r,
                      restrict["rowoff"], restrict["flipped"])]
        else:
            cands = [("rect", w, h, 0.0, False)]
            for off, tag in ((w / 2.0, "offset"), (0.0, "nested")):
                g = gap_search(off, poly)
                if g is not None:
                    cands.append((tag, w, g, off, False))
                if not symmetric:
                    gf = gap_search(off, flip)
                    if gf is not None and (g is None or gf < g - 0.05):
                        cands.append((tag + "-flip", w, gf, off, True))

        for name, px, py, rowoff, flipped in cands:
            ostep = offset_step or max(px, py) / 2.0
            for ox in np.arange(rminx + w / 2.0, rminx + w / 2.0 + px, ostep):
                for oy in np.arange(rminy + h / 2.0, rminy + h / 2.0 + py, ostep):
                    keep, j, y = [], 0, oy
                    while y <= rmaxy - h / 2.0 + 1e-9:
                        fl = 1 if (flipped and j % 2) else 0
                        ph = ox + (rowoff if j % 2 else 0.0)
                        k0 = int(np.ceil((rminx + w / 2.0 - ph) / px - 1e-12))
                        x = ph + k0 * px
                        while x <= rmaxx - w / 2.0 + 1e-9:
                            keep.append((x, y, fl)); x += px
                        y += py; j += 1
                    if len(keep) > best[0]:
                        good = [(x, y, f) for x, y, f in keep
                                if square.covers(translate(flip if f else poly, x, y))]
                        if len(good) > best[0]:
                            reach = 2.0 * max(w, h) + 1.0
                            if _verify_no_overlap(poly, good, reach, flip):
                                best = (len(good), good,
                                        {"lattice": name, "angle": float(ang),
                                         "pitch": (float(px), float(py)),
                                         "rowoff": rowoff, "flipped": flipped})
    return best

def placed_pack(mesh, box=None, clearance=0.2, angle_step=15.0, max_poses=4,
                container=None, packaging=None):
    """Arranged packing: best stable orientation x best lattice x layers.
    container: preset dict (see CONTAINERS) or None -> plain box from `box`.
    packaging: {'part_wrap_mm', 'layer_pad_mm'} — liner applied via apply_packaging."""
    if container is None:
        container = {"type": "box", "w": box[0], "d": box[1], "h": box[2]}
    p = packaging or {}
    wrap = float(p.get("part_wrap_mm", 0.0))
    pad = float(p.get("layer_pad_mm", 0.0))
    cl = clearance + 2.0 * wrap
    H = container["h"] if container["type"] == "box" else container["height"]
    tapered = container["type"] == "frustum"
    poses, probs = resting_orientations(mesh, max_poses)
    results = []
    for k, T in enumerate(poses):
        m = mesh.copy(); m.apply_transform(T)
        part_h = float(m.extents[2])
        layer_h = part_h + cl + pad
        n_layers = int((H + pad) // layer_h)   # pads go BETWEEN layers
        if n_layers == 0:
            continue
        foot = _footprint(m, cl)
        if not tapered:
            region = _container_region(container, 0, H)
            n, centers, meta = pack_layer(foot, region, angle_step)
            if not n:
                continue
            layer_counts = [n] * n_layers
        else:
            # tapered pail: solve the narrowest (bottom) layer fully, then
            # recount the same lattice against each wider layer above
            layer_counts, meta, centers = [], None, None
            for L in range(n_layers):
                z0 = L * layer_h
                region = _container_region(container, z0, z0 + part_h + cl)
                if meta is None:
                    nL, cL, meta = pack_layer(foot, region, angle_step)
                    centers = cL
                else:
                    nL, _, _ = pack_layer(foot, region, angle_step, restrict=meta)
                layer_counts.append(nL)
            if meta is None or not sum(layer_counts):
                continue
        results.append({
            "pose_index": k, "stability": probs[k],
            "per_layer": layer_counts[0], "layers": n_layers,
            "count": int(sum(layer_counts)), "layer_counts": layer_counts,
            "part_height": round(part_h, 3), "lattice": meta,
            "centers": [(float(x), float(y), int(f)) for x, y, f in centers],
            "transform": np.asarray(T).tolist(),
        })
    results.sort(key=lambda r: r["count"], reverse=True)
    return results

# ------------------------------------------------------- poured estimate
# Random-fill fraction vs aspect ratio, anchored to packing literature:
#   sphere RCP 0.64 (Scott & Kilgour; Wikipedia RCP), M&M oblate 1:1.9 -> 0.685
#   (Donev et al., Science 2004), cylinders near AR 1 ~ 0.65-0.67 (sims),
#   rods AR 8 -> 0.467 (Freeman et al. 2019), long rods ~ 1/AR decay.
# AR here = longest extent / shortest extent of the part's bounding box.
_AR_CURVE = [(1.0, 0.64), (1.5, 0.66), (2.0, 0.685), (2.5, 0.64),
             (3.0, 0.60), (4.0, 0.55), (6.0, 0.50), (8.0, 0.467),
             (12.0, 0.39), (16.0, 0.32), (24.0, 0.24), (32.0, 0.19)]

def poured_estimate(mesh, box=None, mode="poured", container=None):
    """Random-fill count estimate. mode: 'poured' (loose) or 'shaken' (dense).
    Works for boxes, drums (cylinder) and pails (frustum)."""
    if container is None:
        container = {"type": "box", "w": box[0], "d": box[1], "h": box[2]}
    if container["type"] == "box":
        vol = container["w"] * container["d"] * container["h"]
        min_dim = min(container["w"], container["d"], container["h"])
    elif container["type"] == "cylinder":
        vol = _container_volume(container)
        min_dim = min(container["diameter"], container["height"])
    else:
        vol = _container_volume(container)
        min_dim = min(container["bottom_diameter"], container["height"])
    ext = np.sort(mesh.extents)
    ar = float(ext[2] / ext[0])
    xs, ys = zip(*_AR_CURVE)
    phi_dense = float(np.interp(ar, xs, ys))
    hull_vol = float(mesh.convex_hull.volume)
    solidity = float(mesh.volume) / hull_vol          # holes/concavity ride along
    # wall effect: ordered/disordered boundary layer wastes space near walls
    d_eq = float((6 * hull_vol / np.pi) ** (1 / 3))
    wall = max(0.80, 1.0 - 0.5 * d_eq / min_dim)
    loose_factor = 0.90 if mode == "poured" else 1.0  # RLP ~ 0.9 x RCP
    phi = phi_dense * loose_factor * wall
    count = int(vol * phi / hull_vol)
    return {"count": count, "fill_fraction_hulls": round(phi, 3),
            "aspect_ratio": round(ar, 2), "solidity": round(solidity, 3),
            "solid_fill_fraction": round(phi * solidity, 3), "mode": mode}

# ------------------------------------------------------- report

def analyze(path, box=None, clearance=0.2, angle_step=15.0, density=None,
            container=None, packaging=None, weight_limit_kg=None):
    mesh = load_mesh(path)
    if container is None and box is not None:
        container = {"type": "box", "w": box[0], "d": box[1], "h": box[2]}
    if weight_limit_kg is None:
        weight_limit_kg = container.get("weight_limit_kg")
    container, packaging = apply_packaging(container, packaging)
    placed = placed_pack(mesh, clearance=clearance, angle_step=angle_step,
                         container=container, packaging=packaging)
    best = placed[0] if placed else None
    out = {
        "part": {
            "file": str(path),
            "extents_mm": [round(float(v), 3) for v in mesh.extents],
            "volume_mm3": round(float(mesh.volume), 2),
            "convex_hull_mm3": round(float(mesh.convex_hull.volume), 2),
            "watertight": bool(mesh.is_watertight),
        },
        "container": container,
        "clearance_mm": clearance,
        "packaging": packaging,
        "placed": best,
        "placed_alternatives": [{k: r[k] for k in
                                 ("pose_index", "per_layer", "layers", "count", "stability")}
                                for r in placed[1:]],
        "poured": poured_estimate(mesh, mode="poured", container=container),
        "shaken": poured_estimate(mesh, mode="shaken", container=container),
    }
    if density:  # g/cm^3 -> part mass and container weight; apply weight caps
        g = float(mesh.volume) / 1000.0 * density
        out["part"]["mass_g"] = round(g, 2)
        if best:
            out["placed"]["total_kg"] = round(g * best["count"] / 1000.0, 1)
        if weight_limit_kg:
            cap = int(weight_limit_kg * 1000.0 / g)
            out["weight_limit_kg"] = weight_limit_kg
            out["max_parts_by_weight"] = cap
            for key in ("placed", "poured", "shaken"):
                r = out.get(key)
                if r and r["count"] > cap:
                    r["count_unlimited"] = r["count"]
                    r["count"] = cap
                    r["weight_limited"] = True
                    if key == "placed":
                        r["total_kg"] = round(g * cap / 1000.0, 1)
    return out, mesh

def main():
    ap = argparse.ArgumentParser(description="PackCheck: parts-per-container calculator")
    ap.add_argument("cad", help=".stp/.step/.stl/.obj part file")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--box", nargs=3, type=float, metavar=("W", "D", "H"),
                   help="inside box dims, mm")
    g.add_argument("--box-inches", nargs=3, type=float, metavar=("W", "D", "H"))
    g.add_argument("--container", choices=sorted(CONTAINERS),
                   help="preset: 55-gal drum, 5-gal pail, gaylord bulk box")
    ap.add_argument("--clearance", type=float, default=0.2,
                    help="air per part, mm (default 0.2; covers typical tolerance)")
    ap.add_argument("--liner", type=float, default=0.0, metavar="MM",
                    help="liner/foam thickness on every wall")
    ap.add_argument("--layer-pad", type=float, default=0.0, metavar="MM",
                    help="pad between layers (chipboard ~0.8, corrugated ~3)")
    ap.add_argument("--wrap", type=float, default=0.0, metavar="MM",
                    help="per-part wrap thickness (bubble ~3-10)")
    ap.add_argument("--ect", type=int, choices=sorted(ECT_LIMIT_KG),
                    help="apply corrugated box gross-weight rating (32/44/48/51)")
    ap.add_argument("--weight-limit", type=float, default=None, metavar="KG",
                    help="hard container weight cap (overrides preset/ECT)")
    ap.add_argument("--angle-step", type=float, default=15.0)
    ap.add_argument("--density", type=float, default=None,
                    help="material g/cm^3 (steel 7.85) for weight output")
    ap.add_argument("--json", metavar="FILE", help="write full result JSON")
    args = ap.parse_args()
    container = None
    box = None
    if args.container:
        container = dict(CONTAINERS[args.container])
    else:
        box = args.box or [v * 25.4 for v in args.box_inches]
    limit = args.weight_limit or (ECT_LIMIT_KG[args.ect] if args.ect else None)
    packaging = {"liner_mm": args.liner, "layer_pad_mm": args.layer_pad,
                 "part_wrap_mm": args.wrap}
    result, _ = analyze(args.cad, box, args.clearance, args.angle_step,
                        args.density, container=container, packaging=packaging,
                        weight_limit_kg=limit)
    if args.json:
        json.dump(result, open(args.json, "w"), indent=1)
    b = result["placed"]
    print(f"Part: {result['part']['extents_mm']} mm, "
          f"{result['part']['volume_mm3']} mm^3")
    c = result["container"]
    print(f"Container: {c['type']} " +
          (f"{c['w']:.0f}x{c['d']:.0f}x{c['h']:.0f}mm" if c["type"] == "box" else
           f"d{c.get('diameter', c.get('top_diameter')):.0f}xh{c['height']:.0f}mm"))
    if b:
        wl = "  ** WEIGHT-LIMITED (geometry would fit "
        wl = wl + f"{b['count_unlimited']:,}) **" if b.get("weight_limited") else ""
        print(f"PLACED : {b['count']:,}  ({b['per_layer']}/layer x {b['layers']} layers, "
              f"lattice={b['lattice']['lattice']}@{b['lattice']['angle']}deg)"
              + (f"  {b['total_kg']}kg" if 'total_kg' in b else "") + wl)
    for key, label in (("shaken", "SHAKEN"), ("poured", "POURED")):
        r = result[key]
        tag = "  ** WEIGHT-LIMITED **" if r.get("weight_limited") else ""
        print(f"{label} : {r['count']:,}{tag}")

if __name__ == "__main__":
    main()
