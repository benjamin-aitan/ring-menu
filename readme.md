# Ring Menu

A prototype hierarchical radial ("ring") menu for tasking against ATR-detected targets, built with PySide6. The window is split into a top-down map of the scene, a simulated drone camera frame, and the mission state. Tap a target's bounding box on the camera frame and nested rings of drone actions open around it: lock an ISR drone on the target (hover and hold, maintain distance/heading, or orbit), or add strike drones. The same target is highlighted on the top-down map. The resulting mission state is shown live as JSON and can be exported to a file.

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
| `radial_menu.py` | The PySide6 demo app: top-down map, camera scene, ring rendering, mission JSON panel and export. Also defines the demo targets and drone lists. |
| `menu_model.py` | Toolkit-independent model (no Qt): mission state, menu node classes, open-ring controller, ring-layout geometry and the camera-to-map `GroundProjection`. |
| `make_scenario.py` | Renders the cartoon ISR camera scene to `inputs/scenario.png`, with a vehicle drawn inside each demo target's bounding box, and the matching top-down map to `inputs/map.png`. |
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

2. Generate the scene images. Images are not committed (`*.png` is ignored), so a fresh clone has no `inputs/scenario.png` or `inputs/map.png` until you create them:

   ```bash
   .venv/bin/python make_scenario.py
   ```

   This writes `inputs/scenario.png` (camera view) and `inputs/map.png` (top-down map). The app still runs without them, but shows a plain grid instead.

All commands in this readme call the environment's interpreter explicitly as `.venv/bin/python`, so there is no need to activate the environment, and they work the same whether or not it is activated.

On Windows, the script needs Git Bash or WSL. In PowerShell, run the equivalent steps by hand: `py -3.13 -m venv .venv`, then `.venv\Scripts\python -m pip install --upgrade pip` and `.venv\Scripts\python -m pip install -r requirements.txt`. Use `.venv\Scripts\python` wherever this readme says `.venv/bin/python`.

## Running the demo

```bash
.venv/bin/python radial_menu.py
```

- The window has three columns: the top-down map on the left, the drone camera view in the middle and the mission JSON on the right.
- Click an ATR bounding box (Tank, Truck or APC) in the camera view to select it and open the first ring around it. The same target's box is painted in its colour on the map. Click it again (or empty ground) to close. The map is display-only.
- The first ring holds the drone actions: **ISR Hover and hold**, **ISR Maintain dist/heading**, **ISR Orbit target** and **Add strike drone**. Each one opens a drone drop-down list straight away.
- An ISR button's list offers the free ISR drones. Picking one locks it on the target in that mode; the button turns green and shows the drone's name. The active mode's list also offers **Cancel ISR lock**. Clicking outside the list changes nothing.
- **Add strike drone** shows a candidate "Select drone…" slot in the next ring next to its list of free strike drones. Picking a drone keeps the slot, and its **Strike timing** and **Strike vector** buttons appear straight away in the next ring, spanning exactly the slot's width. Every assigned drone shows its own pair at the same time; click outside the list instead and the candidate is removed. Click an assigned drone to change or remove it. Tapping an ISR button or an option button leaves the strike rings open. Adding a strike drone marks the target as a strike target; removing its last slot clears that again.
- ISR drones already locked on another target are not offered, and strike drones already assigned are excluded.
- Strike slots fire in order: the first at T+0, each later one after a configurable delay following the previous strike (default 10 s, `0` = simultaneous). **Strike timing** opens a number dialog. The JSON shows `delay_after_previous_s` and the cumulative `strike_offset_s` per drone.
- The right-hand panel shows the current mission state as nested JSON. **Export JSON** writes it to `outputs/mission_<timestamp>.json`.

## Running the tests

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

`QT_QPA_PLATFORM=offscreen` lets the Qt tests run without opening windows. The Qt smoke test also saves `outputs/screenshot_isr.png` and `outputs/screenshot_test.png`, which are handy for checking the rendering.

## Customising

- Demo targets, scene size and drone names live at the top of `radial_menu.py` (`DEMO_TARGETS`, `SCENE_SIZE`, `STRIKE_DRONES`, `ISR_DRONES`). If you move or resize a target, re-run `.venv/bin/python make_scenario.py` so the vehicles stay inside their boxes on both images.
- The top-down map is computed from the camera image by `GroundProjection` in `menu_model.py` (a pinhole camera over flat ground, using the scene's horizon and vanishing point). Its `far_y`, `lateral_range` and `map_scale` set how much ground the map shows and at what size. A target's map box comes from the bottom edge of its ATR box, where the vehicle meets the ground.
- The menu tree for each target is built in `build_target_menu()` in `menu_model.py`. New behaviours are added by subclassing `MenuNode` (or one of `ActionNode`, `ExclusiveOptionNode`, `SelectFromListNode`). Set `align_children = True` on a node to lay its child ring out within the node's own angle instead of fanning it out. Set `always_show_children = True` to show its child ring whenever the node is visible, without a tap.
- Ring sizes and angles are controlled by `RingStyle` in `menu_model.py`.
