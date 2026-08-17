# Boxel

*by AIA Digital Services*

**How many parts fit in a container — and how should they sit?**

Drop in a CAD file (.stp / .step / .stl), pick a container (box, 55-gal drum,
tapered 5-gal pail, or Gaylord), and get a verified packing count, the best
part orientation, and a 3D view of the layout. Handles the real-world gotchas:
liners, layer pads, per-part wrap, and box weight ratings (which for steel
parts usually bind before volume does).

**▶ Try it live:** once GitHub Pages is enabled on this repo, the app runs at
`https://<your-username>.github.io/<repo-name>/` — no install, no upload to any
server. Your CAD file never leaves your browser; all computation is local
JavaScript + WebAssembly.

---

## Using the app

See [docs/Boxel_User_Guide.md](docs/Boxel_User_Guide.md) for the full
walkthrough. Short version: drop a part in, set the container, hit Calculate.
Green number = verified placed count. Orange badge = the weight rating filled
up before the volume did.

## How reliable is it?

See the [reliability report](docs/reliability_report.html): 8 independent test
cases, mean error 2.1%. The geometric engine matches exact lattice mathematics
to 0.00%; the random-fill model is calibrated on packing-physics literature
(sphere RCP 0.64, ellipsoid and rod data) and tested against measured steel
and lead shot bulk densities (within ±2.3%).

## Run the tests yourself

The `engine/` folder holds the Python source of truth — it does everything the
app does plus true concave-silhouette nesting and 180°-flipped rows (finds
2–3× more parts for L-shaped brackets).

```bash
pip install trimesh shapely scipy cascadio mapbox-earcut rtree numpy

python engine/validate.py          # the reliability scorecard
python engine/test_containers.py   # drums, pails, liners, weight caps
python engine/test_complex.py      # concave nesting (camshaft + bracket)
python engine/test_stress.py       # 11 hard parts; needs:
git clone --depth 1 https://github.com/prusa3d/Original-Prusa-i3 prusa

# then try your own part:
python engine/packcheck.py yourpart.stp --box-inches 9 9 9 --density 7.85
python engine/packcheck.py yourpart.stp --container drum55 --density 7.85 --ect 32
```

Note: two scorecard cases reference an M6 hex nut STEP (`nut.stp`) that isn't
included here — drop in any DIN 934 M6 nut model to run those; the demo STL
parts in `engine/` cover everything else.

## Known limits

Placed counts are a verified floor (checked for overlaps and containment) —
not a ceiling. Layers stack flat, so rounded parts that could nest into the
layer below may do ~20% better in reality. Random-fill for extreme shapes
(springs, clips) sits off the calibration curve — pour-test those. And always
measure the container's *inside* dimensions.

## License

MIT for Boxel itself. The app embeds three.js (MIT), quickhull3d (MIT),
and occt-import-js / Open CASCADE (LGPL-2.1) — see THIRD_PARTY_NOTICES.md.
