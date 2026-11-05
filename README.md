# whitebg — Batch White-Background Converter

**English** | [简体中文](README.zh-CN.md)

Turn batches of e-commerce product photos into **clean white-background main images**, fully offline.
`rembg` handles the cutout; this tool adds the delivery-grade post-processing that marketplaces actually
require — subject cropping, consistent padding, square canvas, exact pixel size, soft shadow, and edge
decontamination. Ships with both a desktop GUI and a CLI.

> Everything runs locally. No uploads, no network calls (except the one-time model download).

```
original (any background)  ──▶  cutout  ──▶  crop to subject + padding  ──▶  square / size  ──▶  white or transparent  ──▶  1200×1200 JPG
```

---

## Screenshots

**Main window** — drag-and-drop or file picker on the left, thumbnail wall in the middle (remove any single
image), one-click start at the bottom. Output folder and model can be switched in place.

![Main window](docs/images/ui.png)

**Finished** — the progress bar fills, then reports how many succeeded/failed, total time, and the output
folder, with a button to open it directly.

![Finished](docs/images/ui-done.png)

**Before / after** — left is a casual phone shot against a grey wall; right is the output 1200×1200 pure
white main image, subject auto-centred with even padding on all sides.

![Before and after](docs/images/before-after.jpg)

> ▶ 18-second demo video (1280×720, silent): **[docs/demo.mp4](docs/demo.mp4)**

## Topics covered

The project spans three layers — image processing, desktop application, and packaging/distribution:

| Topic | What it maps to here |
|---|---|
| **Background removal / matting** | `rembg` session wrapper, model selection and reuse, alpha mask post-processing |
| **E-commerce main image production** | Crop to subject, uniform padding ratio, square canvas, exact `N×N`, white compositing, soft shadow |
| **Image post-processing** | Edge decontamination (foreground colour recovery), EXIF orientation, resampling and quality control |
| **ONNX inference** | ONNX Runtime session management, multi-model switching, thread count control, offline weights |
| **Desktop GUI development** | Hand-drawn Tkinter widgets (rounded cards, capsule progress bar), drag-and-drop, worker thread + event pump |
| **Batch processing & automation** | Recursive directory scan, resumable runs (skip existing), `argparse` CLI, multiprocessing |
| **Python project engineering** | Package layout, lazy imports, `pyproject.toml` metadata, unit tests and CI |
| **Packaging & distribution** | PyInstaller one-folder builds, dependency trimming, Windows 7 compatible build with static auditing |

> To make the repo discoverable, paste these into **About → Topics** on GitHub:
> `rembg`, `background-removal`, `image-processing`, `e-commerce`, `product-photography`,
> `onnxruntime`, `tkinter`, `desktop-app`, `batch-processing`, `pyinstaller`

---

## Features

- **Batch processing** — drop in a whole folder; recursive scan, skip already-processed files, optional multiprocessing
- **Two entry points** — Tkinter GUI (drag-and-drop, thumbnail preview, progress bar) or CLI (scriptable, schedulable)
- **Delivery-grade post-processing** — auto crop to subject, uniform padding ratio, square canvas, exact `N×N` pixels, optional soft shadow
- **Edge decontamination** — recovers the foreground colour from alpha, removing background colour bleeding (coloured fringes / halos) on soft edges
- **EXIF orientation fix** — portrait phone shots no longer come out sideways
- **Three models to choose from** — `u2net` (fastest) / `birefnet-general-lite` (balanced, default) / `birefnet-general` (most accurate)
- **Packages into a portable exe** — includes a Windows 7 compatible build config (see [docs/windows7.md](docs/windows7.md))

## What the output looks like

With no arguments you get a standard e-commerce main image: **1200×1200 white JPG**, subject centred,
6% padding on all sides, no shadow. Change the flags for other tastes:

| You want | Flag to add |
|---|---|
| Transparent PNG (for your own layout work) | `--transparent` |
| Keep the original aspect ratio, no square canvas | `--no-square` |
| Uniform 800×800 | `--size 800 --square` |
| A soft drop shadow to avoid the "sticker" look | `--shadow` |
| Fur / hair / lace that needs fine edges | `--alpha-matting` (noticeably slower) |

---

## Requirements

| Item | Requirement |
|---|---|
| OS | Windows 10 / 11 (64-bit). **For Windows 7 use the dedicated build in [docs/windows7.md](docs/windows7.md)** |
| Python | **3.11+** to run from source (required by `rembg 2.0.85`) |
| RAM | 8GB recommended (large images + quality model peak around 2.5GB) |
| Disk | 40MB – 1GB per model, downloaded on demand |
| Network | Only for the initial model download; fully offline afterwards |

## Installation

```bash
git clone https://github.com/jimmyXiang123/whitebg.git
cd whitebg

python -m venv .venv
.venv\Scripts\activate          # PowerShell / cmd
# source .venv/bin/activate     # macOS / Linux (untested)

pip install -r requirements.txt
```

> On first run `rembg` downloads the weights for the selected model. For offline deployment, place them at
> `models/models/<model-name>/<model-name>.onnx` and the program will prefer the local file (no network access).

## Usage

### GUI

```bash
python -m whitebg
```

1. **Drag images or a folder straight into the window**, or click "＋ Add images / Add folder"
2. Pick an output folder and a model ("Speed first" ≈ 2–6 s/image, "Quality first" ≈ 15–20 s/image)
3. Click "Start", then "Open output folder" when it finishes

The first launch takes 30–60 s while the model loads (warm-up happens in the background and the progress bar
shows "loading model"); every image after that is done in seconds.

### CLI

```bash
# Most common: whole folder → 1200×1200 white JPG
python -m whitebg -i input -o output

# Transparent PNG, keep original aspect ratio
python -m whitebg -i input -o output --transparent --format png --no-square

# High-quality model + shadow, try the first 5 images
python -m whitebg -i input -o output -m birefnet-general --shadow --limit 5
```

### Options

| Option | Default | Description |
|---|---|---|
| `-i, --input` | `./input` | Input image or folder |
| `-o, --output` | `./output` | Output folder (created automatically, subdirectory structure preserved) |
| `-m, --model` | `birefnet-general-lite` | Cutout model, see below |
| `-r, --recursive` | off | Recurse into subdirectories |
| `--format` | `jpg` | `png` / `jpg` / `jpeg` / `webp`; defaults to png when transparent |
| `--quality` | `95` | JPG / WebP quality |
| `--size` | `1200` | Longest output edge in pixels, `0` = no resizing |
| `--square` / `--no-square` | on | Whether to fit into a square canvas |
| `--upscale` | off | Enlarge small images to fill the canvas (default only shrinks, to avoid blur) |
| `--margin` | `0.06` | Padding ratio around the subject |
| `--inner-margin` | `0.04` | Extra inset in square mode |
| `--shadow` | off | Add a soft shadow (white background only; cannot combine with `--transparent`) |
| `--transparent` | off | Transparent background, no white fill |
| `--alpha-matting` | off | Fine edges for fur / plush / lace; noticeably slower |
| `--no-decontaminate` | off | Disable edge decontamination (on by default; removes coloured fringes) |
| `--workers` | `1` | Number of worker processes (measured: a single process avoids memory contention and is usually fastest) |
| `--threads` | `0` | ONNX threads per process, `0` = auto |
| `--overwrite` | off | Overwrite existing outputs (skipped by default) |
| `--limit` | `0` | Process only the first N images (for trial runs) |

## Choosing a model

| Model | Size | Speed | Quality | Licence |
|---|---|---|---|---|
| `u2net` | 176MB | Fastest (≈2–6 s) | Slightly hard edges | Apache-2.0, commercial use OK |
| `birefnet-general-lite` | 224MB | Medium (≈15–20 s) | Stable on fine structures, **recommended default** | MIT, commercial use OK |
| `birefnet-general` | 930MB | Slow | Most accurate, good fallback for complex scenes | MIT, commercial use OK |
| `bria-rmbg` | 176MB | Medium | Very high quality | **Commercial use requires a paid BRIA licence** |
| `isnet-general-use` / `silueta` / `u2netp` | small | Fast | Each has weak spots (isnet measured to punch rectangular holes) | See each upstream repo |

> Measured conclusion: for product shots (well-defined subjects) `birefnet-general-lite` is the least
> troublesome; for small images on a plain background `u2net` is faster.

## Building an exe (optional)

```bash
pip install -r requirements-build.txt
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/gui.spec
# Output: dist/白底图转换GUI/ — copy the whole folder and it runs
```

The Windows 7 compatible build needs a Python 3.8 environment; see [docs/windows7.md](docs/windows7.md).
After building, `packaging/scan_win7.py` performs a static audit (checking for leftover Win8+ dependencies).

## Project layout

```
.
├── whitebg/
│   ├── __init__.py        version and metadata (no heavy imports; `import` stays in the millisecond range)
│   ├── engine.py          conversion engine + CLI (PIL/rembg imported lazily inside functions)
│   ├── gui.py             Tkinter GUI
│   ├── theme.py           design tokens: colours, type scale, spacing, breakpoints
│   └── __main__.py        unified entry point for `python -m whitebg`
├── run_gui.py             GUI launcher (PyInstaller points here)
├── run_cli.py             CLI launcher
├── packaging/
│   ├── gui.spec           Win10/11 build config
│   ├── gui_win7.spec      Win7 compatible build config
│   └── scan_win7.py       Win7 compatibility static audit
├── tests/                 unit tests (no model needed, runs in CI)
├── docs/
│   ├── windows7.md        Win7 build: dependency ceilings, requirements, verification log
│   ├── ui.md              design tokens, contrast ratios, component variants, breakpoints
│   └── build.md           packaging in depth
├── requirements.txt       runtime dependencies
├── requirements-win7.txt  pinned versions for the Win7 build
├── README.md              this file (English)
├── README.zh-CN.md        简体中文版
└── pyproject.toml         package metadata / entry points / ruff config
```

`models/`, `input/` and `output/` are runtime data and are excluded via `.gitignore`.

## FAQ

**Q: The subject looks small inside the 1200×1200 canvas.**
By default the tool only shrinks, never enlarges: an original smaller than the canvas is not upscaled
(upscaling only blurs it). Add `--upscale`, or start with larger source images.

**Q: There is a coloured fringe / halo around the edges.**
The background colour bled into the edges (common with green screens and blue walls). Decontamination is on
by default; make sure you have not added `--no-decontaminate`.

**Q: A particular image came out badly (holes / smeared / leftover fragments).**
Every model has weak spots. Try `birefnet-general-lite` or `birefnet-general` first — that solves most cases.
For hair and fur add `--alpha-matting`.

**Q: `python -m whitebg` does not open a window.**
You need a Python build that includes Tk (the official python.org installer bundles it; conda does too).
On Linux install `python3-tk` separately.

**Q: The first run hangs on "loading model".**
It is downloading weights, or compiling JIT code — this is normal. For offline environments, place the models
in `models/` beforehand.

**Q: Why not a single-file exe?**
A single-file build unpacks hundreds of MB into a temp folder on every launch — slow on older machines and
frequently blocked by antivirus. The one-folder build starts faster, is more stable, and is equally portable.

## Development

```bash
pip install -e . --no-deps       # install just this package; tests do not need rembg
python -m unittest discover -s tests -v
ruff check .                     # optional, style check
```

CI (`.github/workflows/ci.yml`) runs the unit tests on Windows with Python 3.11 / 3.12 / 3.13.
No model downloads, results in under a minute.

## Licence

Project code is released under the [MIT License](LICENSE).
The bundled and dependent third-party components (rembg, ONNX Runtime, U-2-Net, BiRefNet, PyMatting, OpenCV,
PyInstaller and others) each carry their own licence and commercial-use conditions — see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Acknowledgements

- [rembg](https://github.com/danielgatis/rembg) — the foundation of the cutout capability
- [U-2-Net](https://github.com/xuebinqin/U-2-Net), [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) — models
- [ONNX Runtime](https://github.com/microsoft/onnxruntime) — inference engine
