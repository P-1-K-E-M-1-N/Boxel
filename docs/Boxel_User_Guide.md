# Boxel — Quick Start Guide

*an AIA Digital Services tool*

Open `index.html` (or the live site) in any browser (Chrome or Edge recommended).
No install, no internet needed — everything runs inside the file.
It answers one question: **how many of this part fit in this container,
and how should they sit?**

---

## The 30-second workflow

1. **Drop in your part** — drag a `.stp`, `.step`, or `.stl` file onto the
   dashed box (or click it to browse). The status line confirms the load
   and shows the triangle count. Dimensions are assumed to be millimeters,
   which is what nearly all CAD exports use.
2. **Pick your container** from the dropdown.
3. **Hit Calculate.** Results appear in the left panel; the 3D view shows
   the actual packing. Drag to orbit, scroll to zoom, use the layer slider
   at the bottom to build the stack up layer by layer.

That's it for a basic run. Everything below is for dialing in accuracy.

---

## Container choices

**Box (custom)** — enter *inside* dimensions, in inches or mm. Measure the
cavity, not the outside of the carton: corrugated walls, bulge, and liners
all steal space.

**55-gal drum / 5-gal pail / Gaylord** — real published inside dimensions
are preloaded. The pail is modeled with its true taper — you'll see the
per-layer count grow from bottom to top (e.g. 551 → 736 for M6 nuts). Each
preset also preloads its typical weight limit, which you can edit.

## Packaging & limits (the gotcha catchers)

- **Liner (mm)** — foam or corrugated lining on the walls. Shrinks the
  cavity on every side. Corrugated pad ≈ 4, foam ≈ 6–25.
- **Layer pad (mm)** — sheets between layers. Chipboard ≈ 0.8,
  corrugated ≈ 3.
- **Part wrap (mm)** — bubble wrap or paper around each part. Applied all
  the way around every part, so even 2mm bites hard on small parts.
- **Clearance per part (mm)** — air between bare parts. The default 0.2
  covers typical ±0.1 machining tolerance. Use 0.5–1.0 for hand-loading,
  2+ for big floppy parts.
- **Density (g/cm³)** — steel 7.85, aluminum 2.70, ABS/nylon ~1.1–1.2,
  zinc 7.14. Needed for weight math.
- **Weight limit (kg)** — hard cap on load weight. Pick a **box strength
  preset** (32/44/48/51 ECT) to fill it automatically, or type your own.
  Blank = no cap.

## Reading the results

- **The big green number** is the placed count — parts arranged in the
  pattern shown in 3D. It's a verified layout (checked for overlaps and
  containment), so treat it as a floor you can promise, not a hope.
- **⚠ weight-limited** — the orange badge means the container's weight
  rating filled up before its volume did. The badge shows what geometry
  alone would hold. For steel parts this fires *constantly* — a 9″ box of
  M6 nuts hits the 65 lb ECT-32 rating at barely half full. When you see
  it, the fix is a stronger box, not a bigger one.
- **Orientation** — which way the part lies and the lattice used
  ("staggered" = honeycomb-style offset rows). This is your answer to
  "how should the parts sit."
- **Per layer × layers** — the stacking recipe. Tapered pails show
  "bottom → top" since layers grow.
- **Shaken / Poured** — random-fill estimates for parts dumped in rather
  than placed: shaken = settled/vibrated, poured = loose dump. Calibrated
  against packing physics and measured bulk densities (±2% on test data).
- **Volume fill / Load weight** — sanity numbers. If load weight looks
  like a back injury, believe it.

## Which number do I quote?

Parts **placed by hand or machine** in patterns → the big placed number.
Parts **dumped in** → quote the poured number (or the poured–shaken range).
Either way, if the ⚠ badge is up, the weight-capped number is the truth.

## Good first test run

Use a part you already know the real-world answer for — a box or pail your
dad's shop has actually filled and counted (or weighed). Run it with the
real carton's inside dims, real liner, and the right ECT preset, and
compare. One known-answer test tells you more than any spec sheet. If the
app's poured number is off by more than ~10–15%, tell me what the real
count was — that's exactly the calibration data the model wants.

## Limits to keep in mind

The app packs complex parts by their convex outline — a safe underestimate.
For L-brackets, cams, and other concave shapes, the Python engine (in the
zip) finds 2–3× more via true-silhouette nesting. Round parts that could
nest into the hollows of the layer below may beat the placed count by up
to ~20% in reality. And on-edge orientations for big flat parts assume
something holds them up, like a rack.
