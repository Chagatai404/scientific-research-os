# Optional adapter: Obsidian Excalidraw

Excalidraw is an **optional presentation adapter**. Research OS installs, validates
and runs identically with it absent. Nothing here installs a plugin; enable
"Excalidraw" yourself in Obsidian if you want it.

## What it is for

- conceptual schematics (mechanisms, pipelines, relationships);
- annotated derivations and coordinate diagrams;
- detector or apparatus schematics;
- annotations laid over a **verified** source figure.

## What it is not for

**Excalidraw is not the default source for quantitative scientific plots.** A
hand-drawn or Excalidraw curve, spectrum, profile or trajectory carries no data.
Quantitative content comes from verified equations or data through the
reproducible-plot route in `references/VISUALIZATION_PROTOCOL.md`.

A drawing remains a schematic unless its quantitative content is itself sourced
from verified equations/data. Label it "schematic, not to scale" where that
matters, and do not let arrows, proportions or spacing imply measured values.

## Registering a drawing

Give the drawing a visual record (`*.visual.json`, see `scripts/visuals.py`):

```json
{
  "visual_schema": 1,
  "visual_id": "VIS-031",
  "title": "Shower development schematic",
  "kind": "conceptual-schematic",
  "concepts": ["physics.hadronic-showers"],
  "source_type": "schematic",
  "verification_status": "inspected",
  "artifact": "assets/visuals/VIS-031-shower.excalidraw.md"
}
```

`visuals.py` rejects an `.excalidraw`/`.excalidraw.md` artifact that is declared
`quantitative` or is a `model-driven-plot` / `simulation-data-visual`. To annotate
a source figure, register the annotated result as a `source-figure` whose
`provenance` cites the original, and keep the original figure unmodified.

## Embedding

Embed the exported image (or the drawing note, if the plugin renders it) with a
standard Obsidian embed and a "What to notice" caption, as for any other teaching
visual. If the plugin is not installed, the exported SVG/PNG still embeds; the
`.excalidraw.md` file is then just a Markdown note and nothing breaks.
