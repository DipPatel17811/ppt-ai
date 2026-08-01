# ppt-ai

A production-grade **AI Presentation Generator** in Python. It takes a topic (or a
fully-specified presentation AST) and produces a professional, *editable* `.pptx`
deck through a deterministic pipeline.

The core design rule:

> The AI never places an object or chooses a coordinate. The AI only emits a typed
> Presentation AST (JSON). Every layout, measurement and coordinate is produced by
> deterministic template-driven code.

This makes output reproducible, validates cleanly, and always produces native
PowerPoint objects (shapes, text, and real charts) that the user can edit — nothing
is rasterised.

## Pipeline

```
topic ──> Planner ──> Presentation AST (JSON) ──> Validator ──> Template
                                                        │
                                                        v
        .pptx <── Compiler (OOXML) <── Layout engine <── Renderer
```

1. **Planner** — builds a `Presentation` AST for a topic. In `ai` mode it asks a
   local HuggingFace model for strict JSON; it degrades automatically to a
   deterministic offline planner (`deterministic` mode) when `torch`/`transformers`
   are not installed.
2. **AST validation** (`validate_presentation`) — checks bullet counts, chart
   consistency, empty fields and structural limits before anything is rendered.
3. **Template selection** — each slide type maps to one of 13 renderers.
4. **Layout engine** (`layout.py`, `utils/geometry.py`) — pure geometry in
   point-space: partition primitives, `FitBox` constraint solving, and an 8pt
   spacing system. Templates work with `Rect`s; they never see EMU.
5. **Renderer / Builder** (`builder.py`) — theme-aware facade that turns layout
   decisions into shapes, text, icons, charts and groups. Every drawn object is
   either a native PowerPoint shape, a native chart, or a group.
6. **Compiler** (`compiler.py`) — the *only* module that touches OOXML. Converts
   point-space geometry to EMU exactly once. Adds native charts, images (fit/fill
   crop), text frames, and group hierarchies.
7. **Motion** — semantic animation plans (`animation.py`) mapped to OOXML timing
   trees, transition effects, and **morph** via stable object IDs assigned by an
   `ObjectIdBank` (`morph_<key>` shape names).
8. **Render validation** (`LayoutValidator`) — re-opens the generated `.pptx` and
   checks out-of-bounds shapes, text-on-text overlap, text overflow and minimum
   font sizes.

## Layout

- `app.py` — CLI entry point.
- `config.py` — constants (aspect ratios, margins, spacing, content limits, fonts).
- `schema.py` — the full Pydantic Presentation AST (13 slide models, discriminated
  union on `type`, chart specs, hierarchy recursion, SWOT quadrants).
- `theme.py` — 7 presets (`corporate`, `slate`, `crimson`, `forest`, `royal`,
  `midnight`, `mono`), color ladders and derived roles; JSON exported to
  `assets/themes/`.
- `templates/` — 13 renderers: `title`, `hero`, `agenda`, `bullets`, `comparison`,
  `timeline`, `process`, `roadmap`, `cycle`, `hierarchy`, `dashboard`, `swot`,
  `conclusion`.
- `builder.py`, `layout.py`, `icons.py`, `charts.py`, `morph.py`, `animation.py`.
- `compiler.py` + `ppt/` (`xml_writer.py`, `transitions.py`, `animations.py`,
  `morph.py`) — the OOXML boundary.
- `ai/` — `planner.py` (deterministic planner + `Planner` facade), `json_generator.py`
  (strict-JSON LLM loop), `validator.py` (fence-stripping, coercion, repair).
- `utils/` — `geometry.py`, `colors.py`, `fonts.py` (Pillow text measurement),
  `spacing.py`.
- `validator.py` — AST + rendered `.pptx` validation.
- `assets/` — `icons/` (SVG subset), `themes/` (generated JSON).

## Install

```powershell
pip install -r requirements.txt
```

## CLI

```powershell
# List what the engine can do
python app.py templates
python app.py themes

# Build a deck from a topic (offline, deterministic)
python app.py generate "Digital Transformation" --mode deterministic -o deck.pptx --validate

# Emit only the Presentation AST
python app.py ast "Digital Transformation" --mode deterministic -o deck.json

# Render an existing AST JSON to .pptx
python app.py build deck.json -o deck.pptx --validate

# Full sample deck covering all templates
python app.py sample -o sample.pptx --theme royal

# Validate a rendered deck
python app.py validate sample.pptx
```

`generate`/`ast` accept `--theme`, `--aspect 16:9|16:10|4:3`, `--sections
title,bullets,process`, `--tone`, and `--json` (AST-only output).

## Tests

Uses the standard library (`unittest`), so no extra install is needed:

```powershell
python -m unittest discover -s tests -t . -p "test_*.py" -v
```
