"""Forge3D — Prompt engineering.

Builds the system + user prompts sent to Ollama. Getting these right is
critical for reliable build123d code generation.
"""

from __future__ import annotations


BUILD123D_SYSTEM_PROMPT = """\
You are Forge3D, an expert CAD programmer specialising in build123d Python library.

RULES YOU MUST FOLLOW:
1. Output ONLY valid Python code inside a ```python code block. No explanations, no prose.
2. Always start with: from build123d import *
3. Always use millimetres for all dimensions unless the user specifies otherwise.
4. Always end your script with: export_step(part.part, str(OUTPUT_PATH))
   where OUTPUT_PATH is defined as: OUTPUT_PATH = Path(__file__).parent / "output.step"
5. Always import Path: from pathlib import Path
6. Use BuildPart() context manager for 3D geometry.
7. Use BuildSketch() context manager for 2D profiles before extruding.
8. Common primitives: Box(l,w,h), Cylinder(r,h), Cone(r1,r2,h), Sphere(r)
9. Position primitives with a `with Locations((x,y,z)):` block, NOT a .translate() call.
10. Boolean operations: add material with the default mode; remove material by passing
    `mode=Mode.SUBTRACT` to the primitive. There are NO standalone add()/subtract()/
    union()/cut() functions — do not call them.
11. AVOID fillet() and chamfer() unless they are essential to the part's function. They are
    the #1 cause of broken scripts. A part WITHOUT fillets/chamfers is still correct and
    acceptable — prefer to omit them. If you absolutely must fillet, select real edges with
    `part.edges().filter_by(Axis.Z)` and pass THOSE — NEVER pass coordinate tuples, numbers,
    or made-up points like fillet([(0,0),(10,0)], ...). That always crashes.
12. Holes: subtract a cylinder — `Cylinder(radius=r, height=H, mode=Mode.SUBTRACT)` inside a
    `with Locations(...)` or `with PolarLocations(...)` block.
13. THROUGH-HOLES MUST FULLY PENETRATE. The cutting cylinder MUST be TALLER than the part it
    passes through — use height = 2 * thickness (or more) and leave it CENTER-aligned. A cutter
    only as tall as the part will, if alignments differ, leave a shallow blind hole instead of a
    through-hole. When in doubt, make the cutter generously taller than the material.

MOST IMPORTANT STRUCTURAL RULE:
- Build the ENTIRE part inside ONE single `with BuildPart() as part:` block.
- Every primitive you create in that block is automatically fused into the result.
- To REMOVE material, pass `mode=Mode.SUBTRACT` to a primitive.
- To position a feature, wrap it in `with Locations((x,y,z)):` or `with PolarLocations(radius, count):`.
- NEVER create several BuildPart objects and try to combine them afterwards.

WHAT NOT TO DO (these are the most common mistakes — avoid them):
- NEVER call .add(), .subtract(), .cut(), .fuse(), .union() as a METHOD on any object
  (e.g. `part.add(x)`, `final_part.add(pipe)`). These methods DO NOT EXIST and will crash.
- NEVER call add()/subtract()/union()/cut() as standalone functions either.
- NEVER pass coordinate tuples or numbers to fillet()/chamfer() (e.g. fillet([(0,0)], r)). When
  unsure, simply DO NOT add fillets or chamfers — omit them.
- NEVER assign primitives to variables and combine them (e.g. `a = Cylinder(...); b = Box(...)`).
  Instead create them directly inside the single BuildPart context.
- Never use show_object(), display(), or any viewer call
- Never use CadQuery syntax (cq.Workplane, etc.) or `import cadquery`
- Never use hard-coded absolute paths
- Never generate geometry outside a BuildPart() context
- Never forget export_step() at the end — without it the STEP file is not created

CORRECT WORKED EXAMPLE (study this exact style — a plate with a centre hole):
```python
from build123d import *
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "output.step"

# Key dimensions (millimetres)
length = 120.0
width = 80.0
thickness = 8.0
hole_diameter = 20.0

with BuildPart() as part:
    # Base plate
    Box(length, width, thickness)
    # Central THROUGH-hole: cutter is taller than the plate so it cuts clean through
    Cylinder(radius=hole_diameter / 2, height=thickness * 2, mode=Mode.SUBTRACT)

export_step(part.part, str(OUTPUT_PATH))
```

ANOTHER CORRECT EXAMPLE (four corner holes using Locations + SUBTRACT):
```python
from build123d import *
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "output.step"

length, width, thickness, hole_r = 100.0, 60.0, 10.0, 4.0
ox, oy = length / 2 - 12, width / 2 - 12

with BuildPart() as part:
    Box(length, width, thickness)
    with Locations((-ox, -oy, 0), (ox, -oy, 0), (-ox, oy, 0), (ox, oy, 0)):
        Cylinder(radius=hole_r, height=thickness * 2, mode=Mode.SUBTRACT)

export_step(part.part, str(OUTPUT_PATH))
```

MULTI-FEATURE EXAMPLE (a flanged pipe connector — ONE BuildPart, NO .add(), several
solids fused by sharing the same context, PolarLocations for an equally-spaced bolt circle):
```python
from build123d import *
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "output.step"

flange_dia = 100.0
flange_thk = 12.0
pipe_od = 50.0
pipe_id = 38.0
pipe_len = 100.0
bolt_pcd = 70.0      # pitch circle diameter
bolt_dia = 6.0

with BuildPart() as part:
    # Flange disc, bottom face on the z=0 plane
    Cylinder(radius=flange_dia / 2, height=flange_thk,
             align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Pipe rising from the flange (same context => fused automatically)
    with Locations((0, 0, flange_thk)):
        Cylinder(radius=pipe_od / 2, height=pipe_len,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Central bore through flange + pipe
    Cylinder(radius=pipe_id / 2, height=flange_thk + pipe_len,
             align=(Align.CENTER, Align.CENTER, Align.MIN),
             mode=Mode.SUBTRACT)
    # Bolt holes equally spaced on the bolt circle. Cutter is taller than the
    # flange (2x) so it always cuts a clean THROUGH-hole.
    with PolarLocations(bolt_pcd / 2, 4):
        Cylinder(radius=bolt_dia / 2, height=flange_thk * 2, mode=Mode.SUBTRACT)

export_step(part.part, str(OUTPUT_PATH))
```
"""


class PromptEngineer:
    """Builds (system, user[, image]) prompt tuples for each input mode."""

    def build_text_prompt(self, user_input: str) -> tuple[str, str]:
        """Return (system_prompt, user_prompt) for a text description."""
        system_prompt = BUILD123D_SYSTEM_PROMPT
        user_prompt = f"""Generate build123d Python code for the following CAD part:

{user_input}

Requirements:
- Output a single self-contained Python script
- Include the OUTPUT_PATH definition at the top
- Include all necessary imports
- The part should be parametric where possible (use variables for key dimensions)
- Add a brief comment above each major geometry step
"""
        return system_prompt, user_prompt

    def build_image_prompt(
        self, user_hint: str, image_b64: str
    ) -> tuple[str, str, str]:
        """Return (system_prompt, user_prompt, image_b64) for an image input."""
        system_prompt = BUILD123D_SYSTEM_PROMPT
        user_prompt = f"""Analyse the attached image carefully. It shows a mechanical part, sketch, or 3D object.

Your task:
1. Identify the overall shape and geometry of the part
2. Estimate dimensions from proportions in the image (use reasonable engineering values)
3. Identify any holes, fillets, chamfers, or special features
4. Generate build123d Python code that reproduces this geometry as a STEP file

Additional context from user: {user_hint if user_hint else 'None provided'}

Important: If you can see dimension annotations in the image, use those exact values.
If no dimensions are visible, estimate based on typical engineering part proportions.
Assume millimetres.
"""
        return system_prompt, user_prompt, image_b64

    def build_pdf_prompt(
        self,
        extracted_text: str,
        page_descriptions: list[str],
        image_b64: str | None = None,
    ) -> tuple[str, str, str | None]:
        """Return (system_prompt, user_prompt, image_b64_or_None) for a PDF drawing."""
        system_prompt = BUILD123D_SYSTEM_PROMPT
        user_prompt = f"""You are given an engineering drawing (technical drawing / blueprint).

EXTRACTED TEXT AND DIMENSIONS FROM THE DRAWING:
{extracted_text}

DRAWING VIEWS IDENTIFIED:
{chr(10).join(page_descriptions)}

Your task:
1. Parse all dimensions from the extracted text (look for numbers followed by units or tolerances)
2. Identify the part's overall dimensions from the front/top/side views
3. Identify features: holes (with diameter and depth), fillets, chamfers, threads
4. Generate build123d Python code that produces a STEP file matching this drawing
5. Use the exact dimensions specified in the drawing — do not estimate if dimensions are given

Common engineering drawing conventions to watch for:
- Ø symbol means diameter
- R before a number means radius
- Dimensions in brackets are reference dimensions
- Dashed lines indicate hidden edges or holes
"""
        return system_prompt, user_prompt, image_b64

    def build_image_description_prompt(
        self, user_hint: str
    ) -> tuple[str, str]:
        """Return (system, user) prompts asking the vision model to DESCRIBE the
        part (not write code). Used as stage 1 of the two-stage image pipeline —
        small vision models reliably describe images but stall when asked to emit
        code directly."""
        system = (
            "You are a senior mechanical design engineer reverse-engineering a part "
            "from a single image. You MUST commit to concrete numbers. There is no "
            "scale bar, so estimate dimensions from typical engineering proportions "
            "and the relative sizes of features in the image. Never say 'unknown' or "
            "'cannot determine' — always give your best engineering estimate.")
        user = (
            "Analyse the part in this image and produce a complete CAD specification.\n\n"
            "1. PART TYPE: name what it is (e.g. flange, bracket, gear, pulley, bushing, "
            "cover plate, shaft, housing).\n"
            "2. BASE SHAPE: the primary solid (round disc / rectangular block / cylinder / "
            "L-bracket / hexagon, etc.) and whether it is symmetric.\n"
            "3. OVERALL DIMENSIONS in millimetres: outer diameter OR length x width, and the "
            "thickness/height. Infer thickness from the part's visible side/edge proportions.\n"
            "4. FEATURES — list EVERY one with numbers:\n"
            "   - central bore / hole: diameter\n"
            "   - bolt/mounting holes: how many, their diameter, and the pitch-circle "
            "diameter (PCD) or x/y positions, and whether equally spaced\n"
            "   - any fillets, chamfers, slots, counterbores, raised hubs, steps\n"
            "5. Estimate feature sizes RELATIVE to the overall size (e.g. each bolt hole looks "
            "about 1/15 of the outer diameter).\n\n"
            "Reply as a short numbered list of concrete values. Do NOT write any code."
        )
        if user_hint:
            user += (f"\n\nThe user added this hint (treat as authoritative where it "
                     f"gives numbers): {user_hint}")
        return system, user

    def build_error_retry_prompt(
        self, original_code: str, error_output: str, attempt_number: int
    ) -> tuple[str, str]:
        """Return (system_prompt, user_prompt) for a post-failure correction."""
        system_prompt = BUILD123D_SYSTEM_PROMPT
        user_prompt = f"""The following build123d Python code produced an error when executed.
Fix the code so it runs correctly and produces a valid STEP file.

ORIGINAL CODE:
```python
{original_code}
```

ERROR OUTPUT:
```
{error_output}
```

Attempt {attempt_number} of 3. Fix the specific error shown above.
Return the complete corrected Python script, not just the changed lines.
"""
        return system_prompt, user_prompt


if __name__ == "__main__":
    pe = PromptEngineer()
    sys_p, user_p = pe.build_text_prompt(
        "A simple bracket 100x60x10mm with 4 holes of diameter 8mm at the corners"
    )
    print("=== SYSTEM PROMPT (first 200 chars) ===")
    print(sys_p[:200])
    print("\n=== USER PROMPT ===")
    print(user_p)
