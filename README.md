# EZCV (Python) — Quickstart

## 1. Set up your environment (one-time)

Open this folder in VS Code, then in the VS Code terminal:

```bash
python -m venv venv
```

Activate it:
- Windows (PowerShell): `venv\Scripts\Activate.ps1`
- Windows (cmd.exe): `venv\Scripts\activate.bat`
- Mac/Linux: `source venv/bin/activate`

You should see `(venv)` appear at the start of your terminal prompt.

Then in VS Code: `Ctrl+Shift+P` → `Python: Select Interpreter` → pick the one with `venv` in its path.

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Run the app

```bash
python main.py
```

A window titled "EZCV - Cyclic Voltammetry Analyzer" should open.

## 4. Try it with the sample data

Click **Import** → leave manufacturer as `Auto-detect` → **Browse...** → pick a file from
`sample_data/` (`sample_chi_2col.txt` or `sample_chi_4col.txt`) → **Import**.

You should see the CV curve plotted, with segment checkboxes above it.

Click **Sample Info** and enter:
- Mass (g): `0.001` (or a real value if you have one)
- Electrode area (cm²): (optional for now)
- V0: `-0.1`
- V1: `1.1`

Then click **Calculate**, tick the parameters you want, and you should see results
appear on the right.

## What's implemented so far
- Import: CHI format (auto-detected) + generic fallback with column-confirmation wizard
- Plotting with segment selection
- Area under curve + specific capacitance calculations
- Sample info panel

## What's not implemented yet (coming next)
- Gamry / Biologic importers (currently show a "coming soon" message)
- Additional calculation modules (energy/power density, ΔEp, diffusion coefficient, etc.)
- PDF report export (button exists, not wired up yet)
- Packaging into a standalone .exe

## If something breaks
Copy the exact error message from the terminal and send it back — that's the fastest way
to debug together.
