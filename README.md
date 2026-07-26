# text-to-cad

Generate real, manufacturable **3D CAD geometry from a text description, a photo, or a PDF drawing** — entirely on your own machine, using a local LLM.

The app asks a local [Ollama](https://ollama.com) model to write a [build123d](https://github.com/gumyr/build123d) script, runs that script in an isolated subprocess, validates the resulting STEP file, and shows it in a 3D viewer. If the generated code crashes, the error is fed back to the model and it tries again.

No cloud APIs. No API keys. Nothing leaves your computer.

---

## Why this is harder than "ask an LLM for code"

An LLM will happily produce build123d code that looks right and doesn't run. The interesting part of this project is everything wrapped around the model:

| Problem | Approach taken |
| --- | --- |
| Models emit prose instead of code | Strict system prompt + code-block extraction, with a sterner re-prompt on the next attempt |
| Generated code crashes | Real `stderr` is fed back into an error-correction prompt and the model retries (default 3 attempts) |
| Generated code is untrusted | Executed in a **separate subprocess**, never `exec()`/`eval()`, with a wall-clock timeout |
| "Success" that produced nothing | STEP file is re-imported with build123d before it counts as a pass |
| Vision models stall on "draw this part" | Two-stage pipeline: vision model *describes* the part in words, text model *writes the code* |
| Small models thrash a low-VRAM GPU | The same model is reused across retries, so no second model load mid-generation |

That last one and the two-stage vision split were both the result of watching small local models fail in specific, reproducible ways — a reasoning-style vision model asked to emit code would "think" indefinitely and return an empty response, so the roles are now split by what each model is actually good at.

---

## Features

- **Three input modes** — plain text prompt, image of a part, or a PDF drawing (text is extracted, and the first page is optionally summarised by the vision model)
- **Local-only inference** via Ollama
- **Self-correcting generation loop** driven by real execution errors
- **Sandboxed execution** of model-written code in a subprocess with a timeout
- **STEP validation** — header check, size sanity check, and a full build123d re-import
- **Built-in 3D viewer** — Three.js + `occt-import-js` (WASM) rendering the STEP file
- **Desktop UI** in PySide6 with drag-and-drop, live streaming log console, generation history, and a settings dialog
- **JSON sidecar** written next to every STEP file recording the model, attempt count, and the exact code that produced it

## Architecture

```
                 ┌───────────────┐
  text ─────────►│               │
  image ────────►│    inputs/    │  normalise → prompt-ready payload
  PDF ──────────►│               │
                 └───────┬───────┘
                         ▼
                 ┌───────────────┐
                 │ PromptEngineer│  system + user prompts, retry prompts
                 └───────┬───────┘
                         ▼
                 ┌───────────────┐
                 │  OllamaClient │  streaming local inference
                 └───────┬───────┘
                         ▼
                 ┌───────────────┐
                 │   CodeRunner  │  isolated subprocess, timeout
                 └───────┬───────┘
                         ▼
                 ┌───────────────┐     fail → error fed back, retry
                 │ StepValidator │────────────────────────┐
                 └───────┬───────┘                        │
                         ▼ pass                           │
                    output.step  ◄────────────────────────┘
```

| Module | Responsibility |
| --- | --- |
| `core/pipeline.py` | Orchestrates one generation request end to end |
| `core/prompt_engineer.py` | Builds system, user, and error-correction prompts |
| `core/ollama_client.py` | Streaming HTTP client for Ollama, code-block extraction |
| `core/code_runner.py` | Runs generated scripts in a subprocess with a timeout |
| `core/step_validator.py` | Verifies the STEP file is real and re-importable |
| `core/inputs/` | Text, image, and PDF input normalisation |
| `ui/` | PySide6 desktop app — panels, widgets, dialogs, 3D viewer |

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- A GPU helps but is not required; the defaults below are chosen to fit in ~6 GB of VRAM

## Setup

```bash
git clone https://github.com/<your-username>/text-to-cad.git
cd text-to-cad

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Pull the models:

```bash
ollama pull llama3.2:latest   # code generation
ollama pull qwen3-vl:4b       # vision (image / drawing understanding)
```

Check everything is wired up:

```bash
python verify_setup.py
```

## Usage

Launch the desktop app:

```bash
python main.py
```

Or run the pipeline headlessly:

```bash
python -m core.pipeline
```

Example prompts that work well:

- `A rectangular plate 120mm long, 80mm wide, 8mm thick with a 20mm diameter hole in the centre`
- `A flange, 150mm outer diameter, 20mm thick, with a 60mm central bore and 6 M10 bolt holes on a 110mm pitch circle`
- `A cylindrical spacer 40mm long, 30mm outer diameter, 16mm inner diameter`

Generated files land in `outputs/` as `<name>.step` plus a `<name>.json` sidecar containing the model used, the attempt count, and the generating code.

## Configuration

All settings live in `.env` (see `.env.example`) and can also be changed from the in-app settings dialog.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server address |
| `TEXT_MODEL` | `llama3.2:latest` | Model used for code generation |
| `VISION_MODEL` | `qwen3-vl:4b` | Model used to describe images and drawings |
| `OUTPUT_DIR` | `./outputs` | Where STEP files are written |
| `TEMP_DIR` | `./temp` | Scratch space for generated scripts |
| `MAX_RETRIES` | `3` | Generation attempts before giving up |
| `CODE_TIMEOUT_SECONDS` | `120` | Wall-clock limit per script execution |

**Model choice matters.** A non-reasoning model for code generation is deliberate — reasoning-style models tend to stall on complex parts and return an empty answer. Larger vision models (8B+) will spill out of a 6 GB card into system RAM and can bring the machine to a crawl.

## Security note

This project executes code written by a language model. That code runs in a **separate subprocess** with a timeout, never via `exec()` or `eval()` in the host process — but it is not a hardened sandbox and it runs with your user's permissions. Run it against models and prompts you trust, and read `outputs/*.json` if you want to see exactly what was executed.

## Limitations

- Complex organic or heavily filleted geometry frequently fails — the prompt actively steers models away from `fillet()`/`chamfer()` because they are the single largest source of broken scripts
- PDF drawing input reads dimensions from text and a vision summary; it does not do true engineering-drawing interpretation
- Output quality scales with model size; small local models handle prismatic parts well and struggle beyond that

## Roadmap

- [ ] Batch generation from a list of prompts
- [ ] Parametric re-generation (tweak a dimension without a new LLM call)
- [ ] STL / 3MF export alongside STEP
- [ ] Prompt library of proven part templates

## License

MIT — see [LICENSE](LICENSE).
