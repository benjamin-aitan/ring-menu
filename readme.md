# Ring Menu

A prototype hierarchical radial ("ring") menu for tasking against ATR-detected targets, built with PySide6. Tap a target's bounding box on a simulated drone video frame and nested rings of actions open around it: show geolocation, lock an ISR drone on the target (hover and hold, maintain distance/heading, or orbit), or set it as a strike target and assign strike drones. The resulting mission state is shown live as JSON and can be exported to a file.

## Repository layout

| File | Purpose |
| --- | --- |
| `radial_menu.py` | The PySide6 demo app: scene, ring rendering, mission JSON panel and export. Also defines the demo targets and drone lists. |
| `menu_model.py` | Toolkit-independent model (no Qt): mission state, menu node classes, open-ring controller and ring-layout geometry. |
| `make_scenario.py` | Renders the cartoon ISR background scene to `inputs/scenario.png`, with a vehicle drawn inside each demo target's bounding box. |
| `test_radial_menu.py` | Pytest suite covering the model, layout geometry, a headless run of the Qt view and the scenario renderer. |
| `requirements.txt` | Python dependencies (`PySide6`, `pytest`). |

## First-time setup

You need Python 3.9 or newer. All commands below are run from the repository root.

1. Create a virtual environment in `.venv/` (this folder is already in `.gitignore`):

   ```bash
   python3 -m venv .venv
   ```

2. Activate it:

   ```bash
   # macOS / Linux
   source .venv/bin/activate

   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   ```

3. Upgrade pip and install the dependencies:

   ```bash
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. Check the install:

   ```bash
   python -c "import PySide6; print(PySide6.__version__)"
   ```

5. Generate the background scene. Images are not committed (`*.png` is ignored), so a fresh clone has no `inputs/scenario.png` until you create it:

   ```bash
   python make_scenario.py
   ```

   This writes `inputs/scenario.png`. The app still runs without it, but you will not see the background scene.

When you come back to the project later, just re-activate the environment (step 2). Run `deactivate` to leave it. If you prefer not to activate, call the interpreter directly, for example `.venv/bin/python radial_menu.py`.

## Running the demo

```bash
python radial_menu.py
```

- Click an ATR bounding box (Tank, Truck or APC) to select it and open the first ring around it. Click it again to close.
- Click a ring button to open the next ring outward. Clicking a sibling closes the deeper rings of the previous branch.
- Options that need a drone (assign ISR drone, strike drone slots) open a drop-down list. ISR drones already locked on another target are not offered, and strike drones already assigned are excluded.
- The right-hand panel shows the current mission state as nested JSON. **Export JSON** writes it to `outputs/mission_<timestamp>.json`.

## Running the tests

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

`QT_QPA_PLATFORM=offscreen` lets the Qt tests run without opening windows. The Qt smoke test also saves `outputs/screenshot_isr.png` and `outputs/screenshot_test.png`, which are handy for checking the rendering.

## Customising

- Demo targets, scene size and drone names live at the top of `radial_menu.py` (`DEMO_TARGETS`, `SCENE_SIZE`, `STRIKE_DRONES`, `ISR_DRONES`). If you move or resize a target, re-run `python make_scenario.py` so the vehicles stay inside their boxes.
- The menu tree for each target is built in `build_target_menu()` in `menu_model.py`. New behaviours are added by subclassing `MenuNode` (or one of `ActionNode`, `ExclusiveOptionNode`, `SelectFromListNode`, `DynamicListNode`).
- Ring sizes and angles are controlled by `RingStyle` in `menu_model.py`.
