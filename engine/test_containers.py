#!/usr/bin/env python3
"""Container & packaging-material tests (the real-world gotchas):
drums, tapered pails, Gaylords, liners, layer pads, part wrap, weight caps."""
import numpy as np
import packcheck as pc

def close(a, b, tol_pct):
    return abs(a - b) / b * 100 <= tol_pct

fails = 0
def check(name, cond, detail=""):
    global fails
    print(f"[{'PASS' if cond else 'FAIL'}] {name:46s} {detail}")
    if not cond:
        fails += 1

d = pc._container_volume(pc.CONTAINERS["drum55"]) / pc.GAL
p = pc._container_volume(pc.CONTAINERS["pail5"]) / pc.GAL
check("drum55 volume ~ 55-58 gal", 55 <= d <= 58.5, f"{d:.2f} gal")
check("pail5 volume ~ 5-6 gal", 5 <= p <= 6.0, f"{p:.2f} gal")

r, mesh = pc.analyze("nut.stp", container=dict(pc.CONTAINERS["drum55"]),
                     clearance=0.2, density=7.85)
check("drum: weight-limited flag set", r["placed"].get("weight_limited") is True,
      f"{r['placed']['count']:,} capped from {r['placed'].get('count_unlimited', 0):,}")
expect = 400 * 1000 / r["part"]["mass_g"]
check("drum: capped count == limit/mass",
      close(r["placed"]["count"], expect, 0.5),
      f"{r['placed']['count']:,} vs {expect:,.0f}")

r2, _ = pc.analyze("nut.stp", container=dict(pc.CONTAINERS["pail5"]),
                   clearance=0.2, density=7.85)
lc = r2["placed"]["layer_counts"]
check("pail: taper monotonicity (top >= bottom)", lc[-1] >= lc[0],
      f"bottom {lc[0]} -> top {lc[-1]}")
check("pail: all layers nonzero", all(n > 0 for n in lc))

base, _ = pc.analyze("door_handle.stl", box=(600, 400, 300), clearance=1.0,
                     density=1.2)
packed, _ = pc.analyze("door_handle.stl", box=(600, 400, 300), clearance=1.0,
                       density=1.2,
                       packaging={"liner_mm": 6, "layer_pad_mm": 3,
                                  "part_wrap_mm": 2})
check("liner+pads+wrap reduce count",
      packed["placed"]["count"] < base["placed"]["count"],
      f"{base['placed']['count']} -> {packed['placed']['count']}")

r3, _ = pc.analyze("nut.stp", box=(228.6, 228.6, 228.6), clearance=0.2,
                   density=7.85, weight_limit_kg=pc.ECT_LIMIT_KG[32])
check("ECT-32 caps 9in nut box at ~12k",
      r3["placed"].get("weight_limited") and 11500 <= r3["placed"]["count"] <= 12500,
      f"{r3['placed']['count']:,} (geometry {r3['placed'].get('count_unlimited',0):,})")

n_poured = r["poured"].get("count_unlimited") or r["poured"]["count"]
liters = pc._container_volume(pc.CONTAINERS["drum55"]) / 1e6
bulk = n_poured * r["part"]["mass_g"] / 1000.0 / liters   # kg/L == g/cm3
check("drum poured bulk density 2.8-3.8 g/cm3", 2.8 <= bulk <= 3.8, f"{bulk:.2f} g/cm3")

print("-" * 70)
print(f"failures: {fails}")
raise SystemExit(1 if fails else 0)
