# Diagram protocol (v0.9.5)

Accurate scientific diagrams: geometry in 2D and 3D, molecules, and biomolecular structure. It adds a *way of making* a figure to
`VISUALIZATION_PROTOCOL.md`, which still owns when a visual is needed, the source-first rule, the verification tiers and the rendered-output
inspection. A figure is **drawn from numbers, and the numbers are checked**: the spec carries the coordinates, atoms and constraints; renderers
only draw them; `scientific_verify.py` checks the same numbers. Drawing a picture proves nothing, and the tools never mark a diagram `verified`.

## The spec (`diagram_schema: 1`)

```json
{"diagram_schema": 1, "id": "VIS-right-triangle", "title": "A 3-4-5 right triangle", "kind": "geometry2d", "units": "cm",
 "points": {"A": [0, 0], "B": [4, 0], "C": [0, 3]}, "segments": [["A", "B"], ["B", "C"], ["C", "A"]], "polygons": [["A", "B", "C"]],
 "angles": [{"at": "A", "from": "B", "to": "C"}],
 "constraints": [{"type": "length", "between": ["B", "C"], "equals": 5}, {"type": "angle", "at": "A", "from": "B", "to": "C", "equals_deg": 90}]}
```

| Kind | Carries | Drawn as |
|---|---|---|
| `geometry2d` | points, segments, polygons, circles, angle marks, constraints | one SVG to scale with equal axes; a right angle gets a square marker; angle values are computed from the coordinates, not typed |
| `geometry3d` | 3D points, segments, polygons, constraints | four orthographic views (front, top, side, isometric) on **one common scale**, right-handed axes with z up, axis triads labelled in each panel |
| `molecule` | atoms (`el`, optional `charge`, `xy` or `xyz`), bonds `[a, b, order]`, optional expected formula, charge and mass | 2D structure with bond orders and charges, or the four 3D views; hydrogens are explicit atoms by default |
| `structure-trace` | per chain `[residue number, x, y, z]` for C-alpha atoms, and the source file's path, SHA-256 and identifier | the C-alpha **backbone trace** in four views (a trace, not a ribbon, surface or electron density), with a different dash per chain |

`"schematic": true` marks a diagram that is not to scale: it is labelled *Schematic, not to scale* and is registered as a conceptual schematic, never
as quantitative. Without it the note says the figure is drawn to scale from the declared coordinates and that rendering is not verification.

## Constraints and checks

Constraint types: `length`, `equal-length`, `angle`, `angle-sum`, `parallel`, `perpendicular`, `incident` (a point on a line or segment), `coplanar`
(3D), `area` (2D polygon). `python scripts/diagram_spec.py verification-spec <spec>` emits the `scientific_verify` spec for the same numbers:

* `geometry-constraint` recomputes each constraint from the coordinates (default tolerance 1e-6 absolute, 1e-6 degrees);
* `molecule-graph` recomputes valence (hydrogens explicit unless `explicit_hydrogens` is false), Hill formula, net charge and molar mass (the
  CIAAW-sourced table in `chembio_verify.py`); an element with no valence rule or no verified weight is `inconclusive`, never guessed;
* `structure-source` binds a **PDB-format file** by its SHA-256 and checks the claims about it: identifier (HEADER), experimental method (EXPDTA),
  resolution (REMARK 2), chains, a residue range (with gaps reported), the SEQRES or observed sequence, and the identity of a numbered residue. Residue
  numbers are PDB numbering, which can differ from a reference sequence's; the check says so when a number is missing. mmCIF is refused, not guessed.

None of these shows that the geometry models the physical object, that a structure is the right protein, or that a database entry is current. The reviewer
states those as not verified.

## Registering, and what a registry record says

`python scripts/diagram_spec.py register <spec> --root <vault> --concept <id>` writes `<id>.diagram.json`, `<id>.svg` and, for 3D scenes, `<id>.viewer.html`
under `Visuals/`, plus a `*.visual.json` record at **`rendered`** with `quantitative: true`, kind `model-driven-plot`, and a basis that names the spec and
its hash. It never overwrites: the same spec is reused, a changed spec for an existing id is refused. Moving to `inspected` and `verified` follows the
verification tiers (`VISUALIZATION_PROTOCOL.md`); link a `verification_record` from a `scientific_verify.py` run that checked this spec.

## The interactive viewer

`<id>.viewer.html` is one self-contained page (no network, no libraries, its own restrictive Content-Security-Policy): drag to rotate, scroll to zoom, arrow
keys, four view buttons. It opens in a browser. Sessions embed the **static SVG views**, because the session page accepts only static SVG; in the Obsidian
companion that is also the only thing a figure can be. Do not expect the viewer to render inside a session.

## Optional capabilities

`python scripts/diagram_spec.py capabilities` lists which of RDKit, PyVista, Matplotlib, Plotly, py3Dmol, Biopython, trimesh, Graphviz (`dot`), Mermaid
(`mmdc`), Inkscape, Blender and Node exist. Nothing here imports, runs or installs them. **Not done:** SMILES depiction (needs RDKit; give an atom graph),
ribbons, surfaces and maps, force-field geometries, pathway layouts (use Mermaid or Graphviz where present), and icon-set illustrations (check each icon set's
licence before use; a biological schematic made of icons never implies quantitative fidelity). Check licences and terms of any database before copying its
content into a figure; cite the entry and version instead.

## Domain recipes

| Need | Use |
|---|---|
| a construction, a solid, a detector or apparatus layout | `geometry2d` / `geometry3d` with constraints for what the lesson relies on (a right angle, equal sides, coplanar faces) |
| a molecule from a source structure | `molecule` with the coordinates and the formula and mass the source states as `expected_*` |
| a protein or nucleic-acid structure | `diagram_spec.py from-pdb file.pdb --id VIS-… --title …`, then `verification-spec` so the file, accession and chains are checked |
| a field, a distribution, a time series | a model-driven plot under `VISUALIZATION_PROTOCOL.md`, not this protocol |
| a mechanism, a pathway, a concept map | a labelled schematic (Excalidraw or Mermaid), marked *schematic, not to scale* |
