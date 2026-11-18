# Ring Menu

A prototype hierarchical radial ("ring") menu for tasking against ATR-detected targets, built with PySide6. Tap a target's bounding box on a simulated drone video frame and nested rings of actions open around it: show geolocation, lock an ISR drone on the target (hover and hold, maintain distance/heading, or orbit), or set it as a strike target and assign strike drones. The resulting mission state is shown live as JSON and can be exported to a file.

## TL:DR

```bash
git clone git@github.com:benjamin-aitan/ring-menu.git
cd ring-menu && ./setup_venv.sh
.venv/bin/python make_scenario.py
.venv/bin/python radial_menu.py
```

## Repository layout

| File | Purpose |
| --- | --- |
| `radial_menu.py` | The PySide6 demo app: scene, ring rendering, mission JSON panel and export. Also defines the demo targets and drone lists. |
| `menu_model.py` | Toolkit-independent model (no Qt): mission state, menu node classes, open-ring controller and ring-layout geometry. |
| `make_scenario.py` | Renders the cartoon ISR background scene to `inputs/scenario.png`, with a vehicle drawn inside each demo target's bounding box. |
| `test_radial_menu.py` | Pytest suite covering the model, layout geometry, a headless run of the Qt view and the scenario renderer. |
| `requirements.txt` | Python dependencies (`PySide6`, `pytest`). |
| `setup_venv.sh` | One-shot setup: creates `.venv/` and installs the requirements. |

## First-time setup

This project uses Python 3.13. A virtual environment does not install Python for you: it is built from a Python that is already on your machine, so install 3.13 first if you don't have it (on macOS: `brew install python@3.13`). Don't rely on the plain `python3` command, which on macOS is often Apple's older built-in Python. All commands below are run from the repository root.

1. Run the setup script. It finds `python3.13`, creates a virtual environment from it in `.venv/` (already in `.gitignore`), upgrades pip, installs `requirements.txt` and checks that PySide6 and pytest import. If an existing `.venv/` was built with a different Python version, the script deletes and rebuilds it:

   ```bash
   cd /path/to/ring-menu/
   ./setup_venv.sh
   ```

   If `python3.13` isn't on your PATH, point the script at it, for example `PYTHON=/opt/homebrew/bin/python3.13 ./setup_venv.sh`. The script refuses to build the environment from any other Python version. It is safe to re-run: it reuses a correct `.venv` and re-syncs the requirements, so run it again after `requirements.txt` changes.

2. Generate the background scene. Images are not committed (`*.png` is ignored), so a fresh clone has no `inputs/scenario.png` until you create it:

   ```bash
   .venv/bin/python make_scenario.py
   ```

   This writes `inputs/scenario.png`. The app still runs without it, but you will not see the background scene.

All commands in this readme call the environment's interpreter explicitly as `.venv/bin/python`, so there is no need to activate the environment, and they work the same whether or not it is activated.

On Windows, the script needs Git Bash or WSL. In PowerShell, run the equivalent steps by hand: `py -3.13 -m venv .venv`, then `.venv\Scripts\python -m pip install --upgrade pip` and `.venv\Scripts\python -m pip install -r requirements.txt`. Use `.venv\Scripts\python` wherever this readme says `.venv/bin/python`.

## Running the demo

```bash
.venv/bin/python radial_menu.py
```

- Click an ATR bounding box (Tank, Truck or APC) to select it and open the first ring around it. Click it again to close.
- Click a ring button to open the next ring outward. Clicking a sibling closes the deeper rings of the previous branch.
- Options that need a drone (assign ISR drone, strike drone slots) open a drop-down list. ISR drones already locked on another target are not offered, and strike drones already assigned are excluded.
- Strike slots fire in order: the first at T+0, each later one after a configurable delay following the previous strike (default 10 s, `0` = simultaneous). Once a drone is chosen, its ring offers a **Strike timing** button that opens a number dialog. The JSON shows `delay_after_previous_s` and the cumulative `strike_offset_s` per drone.
- The right-hand panel shows the current mission state as nested JSON. **Export JSON** writes it to `outputs/mission_<timestamp>.json`.

## Running the tests

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

`QT_QPA_PLATFORM=offscreen` lets the Qt tests run without opening windows. The Qt smoke test also saves `outputs/screenshot_isr.png` and `outputs/screenshot_test.png`, which are handy for checking the rendering.

## Customising

- Demo targets, scene size and drone names live at the top of `radial_menu.py` (`DEMO_TARGETS`, `SCENE_SIZE`, `STRIKE_DRONES`, `ISR_DRONES`). If you move or resize a target, re-run `.venv/bin/python make_scenario.py` so the vehicles stay inside their boxes.
- The menu tree for each target is built in `build_target_menu()` in `menu_model.py`. New behaviours are added by subclassing `MenuNode` (or one of `ActionNode`, `ExclusiveOptionNode`, `SelectFromListNode`, `DynamicListNode`).
- Ring sizes and angles are controlled by `RingStyle` in `menu_model.py`.
