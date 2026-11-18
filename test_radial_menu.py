"""Tests for the ring-menu model, geometry and (headless) Qt view.

Run with ``QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q``.
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence

import pytest

from menu_model import (
    DEFAULT_PROJECTION,
    AddStrikeDroneNode,
    ClickResult,
    DroneSlotNode,
    StrikeTimingNode,
    ExclusiveOptionNode,
    GroundProjection,
    IsrModeNode,
    MenuController,
    MenuNode,
    MenuUI,
    MissionContext,
    RingStyle,
    Target,
    build_target_menu,
    fan_layout,
    ring_fan,
    span_layout,
)

DRONES = ["S1", "S2", "S3"]
ISR = ["I1", "I2", "I3"]


class FakeUI(MenuUI):
    """Scripted stand-in for the Qt UI.

    :param choices: Answers returned by successive dropdowns.
    """

    def __init__(self, choices: Sequence[Optional[str]] = ()) -> None:
        """Store the scripted answers.

        :param choices: Answers returned by successive dropdowns.
        :type choices: Sequence[str or None]
        """
        self.choices = list(choices)
        self.numbers: List[Optional[float]] = []
        self.offered: List[List[str]] = []
        self.messages: List[str] = []
        #: Called on every :meth:`refresh`, e.g. to inspect state mid-click.
        self.on_refresh = lambda: None
        self.refreshes = 0

    def choose_from_list(self, node: MenuNode, options: Sequence[str], current: Optional[str]) -> Optional[str]:
        """Record the options and return the next scripted answer.

        :param node: Requesting node.
        :type node: MenuNode
        :param options: Offered options.
        :type options: Sequence[str]
        :param current: Current choice.
        :type current: str or None
        :returns: Next scripted answer.
        :rtype: str or None
        """
        self.offered.append(list(options))
        return self.choices.pop(0)

    def ask_number(self, title: str, current: float, minimum: float, maximum: float) -> Optional[float]:
        """Return the next scripted number.

        :param title: Prompt.
        :type title: str
        :param current: Pre-filled value.
        :type current: float
        :param minimum: Smallest accepted value.
        :type minimum: float
        :param maximum: Largest accepted value.
        :type maximum: float
        :returns: Next scripted number.
        :rtype: float or None
        """
        return self.numbers.pop(0)

    def refresh(self) -> None:
        """Count the redraw and run the inspection hook."""
        self.refreshes += 1
        self.on_refresh()

    def show_message(self, text: str, modal: bool = False) -> None:
        """Record the message.

        :param text: Message text.
        :type text: str
        :param modal: Ignored.
        :type modal: bool
        """
        self.messages.append(text)


def make_controller(target_id: str = "T1") -> MenuController:
    """Build a controller for a single demo target.

    :param target_id: Identifier of the target.
    :type target_id: str
    :returns: Controller with all rings closed.
    :rtype: MenuController
    """
    target = Target(target_id, "Tank", (0, 0, 10, 10), 1.0, 2.0)
    ctx = MissionContext(target, list(DRONES), available_isr_drones=list(ISR))
    return MenuController(build_target_menu(target), ctx)


def click_isr_mode(ctrl: MenuController, ui: MenuUI, mode_prefix: str) -> MenuNode:
    """Open ring 1 if needed and click one ISR mode (which opens its dropdown).

    :param ctrl: Controller to drive.
    :type ctrl: MenuController
    :param ui: UI passed to the clicks.
    :type ui: MenuUI
    :param mode_prefix: Label prefix of the mode to click, e.g. ``"ISR Orbit"``.
    :type mode_prefix: str
    :returns: The clicked mode node.
    :rtype: MenuNode
    """
    if not ctrl.is_open(ctrl.root):
        ctrl.click(ctrl.root, 0, ui)
    mode = child(ctrl.root, ctrl.ctx, mode_prefix)
    ctrl.click(mode, 1, ui)
    return mode


def child(node: MenuNode, ctx: MissionContext, prefix: str) -> MenuNode:
    """Find a child whose label starts with a prefix.

    :param node: Parent node.
    :type node: MenuNode
    :param ctx: Mission state.
    :type ctx: MissionContext
    :param prefix: Label prefix to look for.
    :type prefix: str
    :returns: The matching child.
    :rtype: MenuNode
    """
    return next(c for c in node.children(ctx) if c.label.startswith(prefix))


# -- geometry ------------------------------------------------------------------


def test_few_options_leave_partial_ring() -> None:
    """Three options at most 50 degrees each cover 150 degrees, centred at the top."""
    layout = fan_layout(3, 90.0, 50.0)
    assert [s for _, s in layout] == [50.0, 50.0, 50.0]
    assert layout[0][0] + 50.0 == pytest.approx(165.0)  # left edge
    assert layout[-1][0] == pytest.approx(15.0)  # right edge


def test_many_options_split_full_circle() -> None:
    """Twelve options split 360 degrees evenly."""
    layout = fan_layout(12, 90.0, 50.0)
    assert all(s == pytest.approx(30.0) for _, s in layout)
    assert sum(s for _, s in layout) == pytest.approx(360.0)


def test_fan_is_clockwise_and_centred() -> None:
    """Index 0 is left of centre and the fan's middle is the centre angle."""
    layout = fan_layout(4, 30.0, 20.0, gap_deg=2.0)
    mids = [start + sweep / 2.0 for start, sweep in layout]
    assert mids == sorted(mids, reverse=True)
    assert (mids[0] + mids[-1]) / 2.0 == pytest.approx(30.0)
    assert all(sweep == pytest.approx(18.0) for _, sweep in layout)


def test_outer_rings_use_smaller_angles() -> None:
    """Button arc length is capped in pixels, so outer rings get smaller angles."""
    style = RingStyle()
    inner = ring_fan(2, 1, 90.0, style)[0][1]
    outer = ring_fan(2, 3, 90.0, style)[0][1]
    assert outer < inner


def test_span_layout_fills_parent_angle_exactly() -> None:
    """Buttons split a span with outer edges on the span's edges and gaps only between them."""
    layout = span_layout(2, 30.0, 40.0, gap_deg=4.0)
    assert layout == [pytest.approx((52.0, 18.0)), pytest.approx((30.0, 18.0))]
    assert span_layout(1, 30.0, 40.0, gap_deg=4.0) == [(30.0, 40.0)]
    assert span_layout(0, 30.0, 40.0) == []


def test_projection_maps_lower_boxes_nearer() -> None:
    """A box lower in the camera image is nearer the camera, so lower on the map."""
    proj = GroundProjection()
    _, far_y = proj.to_map(700, 300)
    _, near_y = proj.to_map(700, 600)
    assert near_y > far_y
    assert proj.camera()[1] == pytest.approx(proj.map_size[1])


def test_projection_keeps_vanishing_lines_parallel() -> None:
    """Points on one line through the vanishing point share a map x (the road is straight)."""
    proj = GroundProjection()
    vx, hy = proj.vanishing_x, proj.horizon_y
    xs = [proj.to_map(vx + 0.5 * (y - hy), y)[0] for y in (200, 400, 780)]
    assert xs == pytest.approx([xs[0]] * 3)
    with pytest.raises(ValueError):
        proj.to_map(100, hy)


def test_demo_targets_fit_on_map_without_overlap() -> None:
    """Every demo target's map box lies inside the map and no two overlap."""
    import radial_menu

    width, height = DEFAULT_PROJECTION.map_size
    rects = [DEFAULT_PROJECTION.target_map_rect(t.rect) for t in radial_menu.DEMO_TARGETS]
    for x, y, w, h in rects:
        assert 0 <= x and x + w <= width and 0 <= y and y + h <= height
    for i, (ax, ay, aw, ah) in enumerate(rects):
        for bx, by, bw, bh in rects[i + 1:]:
            assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay


# -- model and controller ------------------------------------------------------


def test_center_click_toggles_first_ring() -> None:
    """Clicking the root opens ring 1 (the drone actions); clicking again closes it."""
    ctrl = make_controller()
    ui = FakeUI()
    ctrl.click(ctrl.root, 0, ui)
    assert [r.level for r in ctrl.rings()] == [1]
    nodes = ctrl.rings()[0].nodes
    assert [n.label.split("\n")[0] for n in nodes] == ["ISR Hover", "ISR Maintain", "ISR Orbit", "Add strike"]
    assert all(isinstance(n, IsrModeNode) and n.children(ctrl.ctx) == [] for n in nodes[:3])
    assert isinstance(nodes[3], AddStrikeDroneNode)
    ctrl.click(ctrl.root, 0, ui)
    assert ctrl.rings() == []


def test_generic_exclusive_option_toggles_off() -> None:
    """The generic ExclusiveOptionNode still clears its value when reselected."""
    ctrl = make_controller()
    ui = FakeUI()
    node = ExclusiveOptionNode("X", "isr_mode", "x")
    node.on_click(ctrl.ctx, ui)
    assert ctrl.ctx.isr_mode == "x"
    node.on_click(ctrl.ctx, ui)
    assert ctrl.ctx.isr_mode is None


def test_isr_button_assigns_drone_from_dropdown() -> None:
    """An ISR button opens the drone dropdown at once; picking a drone locks it in that mode."""
    ctrl = make_controller()
    ui = FakeUI(choices=["I2", "I3"])
    hover = click_isr_mode(ctrl, ui, "ISR Hover")
    assert ui.offered[0] == ["I1", "I2", "I3"]  # no cancel entry: nothing locked yet
    assert (ctrl.ctx.isr_mode, ctrl.ctx.isr_drone) == ("hover_hold", "I2")
    assert hover.is_selected(ctrl.ctx)
    assert hover.display_label(ctrl.ctx) == "ISR Hover\nand hold\nI2"
    assert ctrl.open_path == [ctrl.root]  # ISR buttons have no ring of their own

    orbit = click_isr_mode(ctrl, ui, "ISR Orbit")  # switching mode takes the new pick
    assert (ctrl.ctx.isr_mode, ctrl.ctx.isr_drone) == ("orbit", "I3")
    assert not hover.is_selected(ctrl.ctx) and hover.display_label(ctrl.ctx) == hover.label
    assert orbit.is_selected(ctrl.ctx)


def test_dismissed_isr_dropdown_changes_nothing() -> None:
    """Clicking outside the ISR dropdown leaves the lock as it was."""
    ctrl = make_controller()
    ui = FakeUI(choices=["I1", None, None])
    click_isr_mode(ctrl, ui, "ISR Orbit")
    click_isr_mode(ctrl, ui, "ISR Orbit")
    click_isr_mode(ctrl, ui, "ISR Hover")
    assert (ctrl.ctx.isr_mode, ctrl.ctx.isr_drone) == ("orbit", "I1")


def test_isr_drone_on_other_target_is_not_offered() -> None:
    """An ISR drone locked on one target is excluded from other targets' dropdowns."""
    t1, t2 = make_controller("T1"), make_controller("T2")
    contexts = {"T1": t1.ctx, "T2": t2.ctx}
    for tid, ctx in contexts.items():
        ctx.drones_taken_elsewhere = (
            lambda kind, me=tid: [c.isr_drone for k, c in contexts.items() if k != me and c.isr_drone]
            if kind == "isr" else []
        )
    ui = FakeUI(choices=["I1", "I3"])
    click_isr_mode(t1, ui, "ISR Hover")
    click_isr_mode(t2, ui, "ISR Orbit")
    assert ui.offered[1] == ["I2", "I3"]
    assert (t1.ctx.isr_drone, t2.ctx.isr_drone) == ("I1", "I3")


def test_cancel_isr_lock_only_on_active_mode() -> None:
    """Only the active mode's dropdown offers cancel; choosing it clears mode and drone."""
    ctrl = make_controller()
    ui = FakeUI(choices=["I1", "I1", IsrModeNode.CANCEL])
    click_isr_mode(ctrl, ui, "ISR Maintain")
    click_isr_mode(ctrl, ui, "ISR Maintain")
    assert ui.offered[1] == ["I1", "I2", "I3", IsrModeNode.CANCEL]
    click_isr_mode(ctrl, ui, "ISR Maintain")
    assert ctrl.ctx.isr_mode is None and ctrl.ctx.isr_drone is None
    assert ctrl.ctx.free_isr_drones() == ISR


def test_add_strike_drone_shows_candidate_then_keeps_assigned_slot() -> None:
    """Add shows a candidate slot during the dropdown; a picked drone keeps the slot."""
    ctrl = make_controller()
    ui = FakeUI(choices=["S2", "S1"])
    add = child(ctrl.root, ctrl.ctx, "Add strike")
    seen = []
    ui.on_refresh = lambda: seen.append([n.display_label(ctrl.ctx) for r in ctrl.rings() for n in r.nodes if r.parent is add])

    ctrl.click(ctrl.root, 0, ui)
    assert ctrl.click(add, 1, ui) is ClickResult.OPEN
    assert seen[0] == ["Select\ndrone…"]  # the candidate wedge is drawn next to the dropdown
    assert ui.offered[0] == ["S1", "S2", "S3"]
    assert ctrl.ctx.is_strike_target and add.is_selected(ctrl.ctx)
    assert ctrl.open_path == [ctrl.root, add]

    ctrl.click(add, 1, ui)
    assert seen[1] == ["S2", "Select\ndrone…"]
    assert ui.offered[1] == ["S1", "S3"]  # S2 is taken by the first slot
    slots = next(r.nodes for r in ctrl.rings() if r.parent is add)
    assert all(isinstance(s, DroneSlotNode) for s in slots)
    assert [a.drone_id for a in ctrl.ctx.strike_assignments] == ["S2", "S1"]
    assert add.children(ctrl.ctx) == slots  # cached, identical objects


def test_dismissed_strike_dropdown_drops_candidate() -> None:
    """Clicking outside the strike dropdown removes the candidate slot only."""
    ctrl = make_controller()
    ui = FakeUI(choices=[None, "S3", None])
    add = child(ctrl.root, ctrl.ctx, "Add strike")
    ctrl.click(ctrl.root, 0, ui)
    assert ctrl.click(add, 1, ui) is ClickResult.CLOSE
    assert ctrl.ctx.strike_assignments == [] and not ctrl.ctx.is_strike_target
    assert ctrl.open_path == [ctrl.root]

    ctrl.click(add, 1, ui)
    ctrl.click(add, 1, ui)  # dismissed: the S3 slot stays, the ring stays open
    assert [a.drone_id for a in ctrl.ctx.strike_assignments] == ["S3"]
    assert ctrl.open_path == [ctrl.root, add]


def test_slot_options_show_as_soon_as_drone_is_picked() -> None:
    """Each assigned drone shows its timing and vector buttons with no extra tap."""
    ctrl = make_controller()
    ui = FakeUI(choices=["S1", "S2"])
    add = child(ctrl.root, ctrl.ctx, "Add strike")
    ctrl.click(ctrl.root, 0, ui)
    ctrl.click(add, 1, ui)
    first = add.children(ctrl.ctx)[0]
    assert first.align_children and first.always_show_children
    assert [(r.level, r.parent) for r in ctrl.rings()] == [(1, ctrl.root), (2, add), (3, first)]
    assert [n.label.split("\n")[0] for n in ctrl.rings()[-1].nodes] == ["Strike", "Strike"]

    ctrl.click(add, 1, ui)  # second drone: both slots show their options
    second = add.children(ctrl.ctx)[1]
    assert [(r.level, r.parent) for r in ctrl.rings()[2:]] == [(3, first), (3, second)]
    assert ctrl.open_path == [ctrl.root, add]  # slots never join the open path


def test_ringless_taps_keep_strike_rings_open() -> None:
    """ISR taps, option taps and a dismissed add leave the strike rings on screen."""
    ctrl = make_controller()
    ui = FakeUI(choices=["S1", "S2", "I1", None])
    ui.numbers = [3.0]
    add = child(ctrl.root, ctrl.ctx, "Add strike")
    ctrl.click(ctrl.root, 0, ui)
    ctrl.click(add, 1, ui)
    ctrl.click(add, 1, ui)
    shown = [(r.level, r.parent) for r in ctrl.rings()]

    click_isr_mode(ctrl, ui, "ISR Orbit")
    assert ctrl.ctx.isr_drone == "I1"
    assert [(r.level, r.parent) for r in ctrl.rings()] == shown

    second = add.children(ctrl.ctx)[1]
    timing = second.children(ctrl.ctx)[0]
    ctrl.click(timing, 3, ui)
    assert ctrl.ctx.strike_assignments[1].delay_s == 3.0
    assert [(r.level, r.parent) for r in ctrl.rings()] == shown

    ctrl.click(add, 1, ui)  # dismissed: candidate dropped, existing drones kept
    assert [a.drone_id for a in ctrl.ctx.strike_assignments] == ["S1", "S2"]
    assert [(r.level, r.parent) for r in ctrl.rings()] == shown


def test_strike_timing_sequence_is_configurable() -> None:
    """Later slots strike after a configurable delay; offsets accumulate."""
    ctrl = make_controller()
    ctx = ctrl.ctx
    first, second, third = ctx.add_slot(), ctx.add_slot(), ctx.add_slot()
    for slot, drone in zip((first, second, third), DRONES):
        slot.drone_id = drone
    assert ctx.strike_offsets() == {1: 0.0, 2: 10.0, 3: 20.0}  # default 10 s gap

    node = StrikeTimingNode(second.slot_id)
    ui = FakeUI()
    ui.numbers = [4.5]
    assert node.display_label(ctx).startswith("+10 s")
    node.run(ctx, ui)
    assert second.delay_s == 4.5 and node.display_label(ctx).startswith("+4.5 s")
    ui.numbers = [None]  # cancelled dialog leaves the value alone
    node.run(ctx, ui)
    assert second.delay_s == 4.5
    assert ctx.strike_offsets() == {1: 0.0, 2: 4.5, 3: 14.5}

    first_node = StrikeTimingNode(first.slot_id)  # first strike has nothing to configure
    first_node.run(ctx, ui)
    assert first_node.display_label(ctx).startswith("Strike at")
    drones = ctx.to_dict()["strike"]["drones"]
    assert [(d["delay_after_previous_s"], d["strike_offset_s"]) for d in drones] == [
        (None, 0.0), (4.5, 4.5), (10.0, 14.5)
    ]

    ctx.remove_slot(first.slot_id)  # next slot becomes the first strike
    assert ctx.strike_offsets() == {2: 0.0, 3: 10.0}


def test_removing_slot_drops_its_options() -> None:
    """Removing a slot removes it and its options; removing the last closes the strike ring."""
    ctrl = make_controller()
    ui = FakeUI(choices=["S1", DroneSlotNode.REMOVE])
    add = child(ctrl.root, ctrl.ctx, "Add strike")
    ctrl.click(ctrl.root, 0, ui)
    ctrl.click(add, 1, ui)
    slot = add.children(ctrl.ctx)[0]
    assert any(r.parent is slot for r in ctrl.rings())
    ctrl.click(slot, 2, ui)
    assert ctrl.ctx.strike_assignments == []
    assert not ctrl.ctx.is_strike_target  # no slots left, so no longer a strike target
    assert ctrl.open_path == [ctrl.root]  # the now-empty slot ring collapses too
    assert [r.parent for r in ctrl.rings()] == [ctrl.root]


def test_to_dict_shape() -> None:
    """The exported dict has target, ISR and strike sections."""
    ctrl = make_controller()
    ctrl.ctx.isr_mode = "hover_hold"
    ctrl.ctx.isr_drone = "I1"
    ctrl.ctx.add_slot().drone_id = "S3"
    d = ctrl.ctx.to_dict()
    assert d["target"]["geo"] == {"lat": 1.0, "lon": 2.0}
    assert d["isr_lock"] == {"locked": True, "mode": "hover_hold", "drone_id": "I1"}
    assert d["strike"]["drones"] == [{"slot": 1, "drone_id": "S3", "vector": None, "delay_after_previous_s": None, "strike_offset_s": 0.0}]


# -- Qt smoke test ---------------------------------------------------------------


def test_qt_view_renders_and_saves_screenshot() -> None:
    """Drive the real view headlessly and save a screenshot to ``outputs/``."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import radial_menu

    app = QApplication.instance() or QApplication([])
    window = radial_menu.MainWindow()
    view = window.view
    ui = FakeUI(choices=["ISR-02", "Strike-02", "Strike-04"])
    view.choose_from_list = ui.choose_from_list  # avoid a blocking QMenu

    # One tap selects the target and opens ring 1; a second tap closes it.
    ctrl = view.controllers["T1"]
    view.select_target("T1")
    assert view.active_id == "T1" and ctrl.open_path == [ctrl.root]
    view.select_target("T1")
    assert view.active_id is None
    view.select_target("T2")
    assert view.active_id == "T2"
    assert view.controllers["T2"].open_path == [view.controllers["T2"].root]

    # The map paints the selected target's box and clears it on deselect.
    assert window.map_view.active_id == "T2"
    t2_item = window.map_view.items_by_id["T2"]
    assert t2_item.pen().color().name() == radial_menu.DEMO_TARGETS[1].color
    assert window.map_view.items_by_id["T1"].pen().color().name() == radial_menu.COLORS["bbox"]
    view.select_target(None)
    assert window.map_view.active_id is None
    assert t2_item.pen().color().name() == radial_menu.COLORS["bbox"]

    view.select_target("T1")
    assert window.map_view.active_id == "T1"
    view.click_node(child(ctrl.root, ctrl.ctx, "ISR Orbit"), 1)  # dropdown -> ISR-02
    assert view.mission_dict()["targets"]["T1"]["isr_lock"]["drone_id"] == "ISR-02"
    out = radial_menu.OUTPUT_DIR
    out.mkdir(exist_ok=True)
    window.show()
    app.processEvents()
    assert window.grab().save(str(out / "screenshot_isr.png"))

    add = child(ctrl.root, ctrl.ctx, "Add strike")
    view.click_node(add, 1)  # dropdown -> Strike-02
    view.click_node(add, 1)  # dropdown -> Strike-04
    slots = add.children(ctrl.ctx)

    # Every drone's timing/vector buttons show at once, each spanning its slot's angle.
    segments = {item.node: item for item in view._menu_items}
    for slot in slots:
        opts = [segments[n] for n in slot.children(ctrl.ctx)]
        assert len(opts) == 2 and all(o.level == 3 for o in opts)
        edges = sorted(a for o in opts for a in (o.angles[0], o.angles[0] + o.angles[1]))
        start, sweep = segments[slot].angles
        assert edges[0] == pytest.approx(start) and edges[-1] == pytest.approx(start + sweep)

    assert '"Strike-02"' in window.json_box.toPlainText()
    assert view.mission_dict()["targets"]["T1"]["isr_lock"]["mode"] == "orbit"
    app.processEvents()
    assert window.grab().save(str(out / "screenshot_test.png"))


def test_scenario_draws_vehicle_in_each_box() -> None:
    """The scenario image matches the scene size and has a vehicle in each box."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import make_scenario
    import radial_menu

    app = QApplication.instance() or QApplication([])  # noqa: F841 (keeps Qt alive)
    image = make_scenario.render_scenario(radial_menu.DEMO_TARGETS, radial_menu.SCENE_SIZE)
    assert (image.width(), image.height()) == tuple(int(v) for v in radial_menu.SCENE_SIZE)
    for target in radial_menu.DEMO_TARGETS:
        x, y, w, h = target.rect
        # Count pixels in the box that differ clearly from the surrounding ground.
        ground = image.pixelColor(int(x - 30), int(y + h / 2))
        differing = 0
        for px in range(int(x), int(x + w), 4):
            for py in range(int(y), int(y + h), 4):
                c = image.pixelColor(px, py)
                if abs(c.red() - ground.red()) + abs(c.green() - ground.green()) + abs(c.blue() - ground.blue()) > 60:
                    differing += 1
        assert differing > 40, f"no vehicle drawn in {target.target_id}'s box"


def test_map_draws_vehicle_in_each_footprint() -> None:
    """The map image has the projection's size and a vehicle in each target footprint."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    import make_scenario
    import radial_menu

    app = QApplication.instance() or QApplication([])  # noqa: F841 (keeps Qt alive)
    image = make_scenario.render_map(radial_menu.DEMO_TARGETS)
    width, height = DEFAULT_PROJECTION.map_size
    assert (image.width(), image.height()) == (round(width), round(height))
    for target in radial_menu.DEMO_TARGETS:
        x, y, w, h = DEFAULT_PROJECTION.target_footprint(target.rect)
        ground = image.pixelColor(int(x - 12), int(y + h / 2))
        differing = 0
        for px in range(int(x) + 1, int(x + w) - 1, 2):
            for py in range(int(y) + 1, int(y + h) - 1, 2):
                c = image.pixelColor(px, py)
                if abs(c.red() - ground.red()) + abs(c.green() - ground.green()) + abs(c.blue() - ground.blue()) > 60:
                    differing += 1
        assert differing > 20, f"no vehicle drawn in {target.target_id}'s map footprint"
