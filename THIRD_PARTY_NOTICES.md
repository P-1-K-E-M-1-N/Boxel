# Third-party software embedded in index.html

- **three.js** (MIT) — 3D rendering. https://threejs.org
- **quickhull3d** (MIT) — convex hulls. https://www.npmjs.com/package/quickhull3d
- **occt-import-js** (LGPL-2.1, bundling Open CASCADE Technology) — STEP file
  parsing via WebAssembly. https://github.com/kovacsv/occt-import-js
  Full license texts: `docs/license.occt-import-js.txt`, `docs/license.occt.txt`

The Python engine depends on trimesh, shapely, scipy, numpy, cascadio,
mapbox-earcut, and rtree, installed separately via pip (see engine/).
