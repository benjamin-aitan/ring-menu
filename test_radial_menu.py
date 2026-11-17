"""Tests for the ring-menu model, geometry and (headless) Qt view.

Run with ``QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q``.
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence

import pytest

from menu_model import (
    ClickResult,
    AssignIsrDroneNode,
    DroneSlotNode,
    DynamicListNode,
    ExclusiveOptionNode,
    MenuController,
    MenuNode,
    MenuUI,
    MissionContext,
    RingStyle,
    Target,
    build_target_menu,
    fan_layout,
    ring_fan,
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
        self.offered: List[List[str]] = []
        self.messages: List[str] = []

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


def open_isr_mode(ctrl: MenuController, ui: MenuUI, mode_prefix: str) -> MenuNode:
    """Open the ISR branch and click one ISR mode.

    :param ctrl: Controller to drive.
    :type ctrl: MenuController
    :param ui: UI passed to the clicks.
    :type ui: MenuUI
    :param mode_prefix: Label prefix of the mode to click.
    :type mode_prefix: str
    :returns: The clicked mode node.
    :rtype: MenuNode
    """
    isr = child(ctrl.root, ctrl.ctx, "Lock ISR")
    if not ctrl.is_open(ctrl.root):
        ctrl.click(ctrl.root, 0, ui)
    if not ctrl.is_open(isr):
        ctrl.click(isr, 1, ui)
    mode = child(isr, ctrl.ctx, mode_prefix)
    ctrl.click(mode, 2, ui)
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


# -- model and controller ------------------------------------------------------


def test_center_click_toggles_first_ring() -> None:
    """Clicking the root opens ring 1; clicking again closes it."""
    ctrl = make_controller()
    ui = FakeUI()
    ctrl.click(ctrl.root, 0, ui)
    assert [r.level for r in ctrl.rings()] == [1]
    assert len(ctrl.rings()[0].nodes) == 3
    ctrl.click(ctrl.root, 0, ui)
    assert ctrl.rings() == []


def test_opening_sibling_truncates_path() -> None:
    """Opening a different ring-1 button closes the previous branch."""
    ctrl = make_controller()
    ui = FakeUI()
    ctrl.click(ctrl.root, 0, ui)
    isr = child(ctrl.root, ctrl.ctx, "Lock ISR")
    strike = child(ctrl.root, ctrl.ctx, "Set as strike")
    ctrl.click(isr, 1, ui)
    assert ctrl.open_path == [ctrl.root, isr]
    ctrl.click(strike, 1, ui)
    assert ctrl.open_path == [ctrl.root, strike]
    assert ctrl.ctx.is_strike_target


def test_generic_exclusive_option_toggles_off() -> None:
    """The generic ExclusiveOptionNode still clears its value when reselected."""
    ctrl = make_controller()
    ui = FakeUI()
    node = ExclusiveOptionNode("X", "isr_mode", "x")
    node.on_click(ctrl.ctx, ui)
    assert ctrl.ctx.isr_mode == "x"
    node.on_click(ctrl.ctx, ui)
    assert ctrl.ctx.isr_mode is None


def test_isr_mode_opens_assign_ring_and_switching_keeps_drone() -> None:
    """Picking a mode opens 'Assign ISR drone'; switching modes keeps the drone."""
    ctrl = make_controller()
    ui = FakeUI(choices=["I2"])
    hover = open_isr_mode(ctrl, ui, "Hover")
    assert ctrl.ctx.isr_mode == "hover_hold"
    assert ctrl.open_path[-1] is hover
    assign = ctrl.rings()[-1].nodes[0]
    assert isinstance(assign, AssignIsrDroneNode)
    assert assign.display_label(ctrl.ctx) == "Assign\nISR drone"

    ctrl.click(assign, 3, ui)
    assert ui.offered[0] == ["I1", "I2", "I3", AssignIsrDroneNode.CANCEL]
    assert ctrl.ctx.isr_drone == "I2"
    assert assign.display_label(ctrl.ctx) == "I2" and assign.is_selected(ctrl.ctx)

    orbit = open_isr_mode(ctrl, ui, "Orbit")
    assert ctrl.ctx.isr_mode == "orbit" and ctrl.ctx.isr_drone == "I2"
    assert not hover.is_selected(ctrl.ctx) and hover.children(ctrl.ctx) == []
    assert ctrl.open_path[-1] is orbit


def test_clicking_active_isr_mode_toggles_ring_only() -> None:
    """Clicking the active mode hides/shows its ring but keeps the mode."""
    ctrl = make_controller()
    ui = FakeUI()
    orbit = open_isr_mode(ctrl, ui, "Orbit")
    ctrl.click(orbit, 2, ui)
    assert ctrl.ctx.isr_mode == "orbit" and not ctrl.is_open(orbit)
    ctrl.click(orbit, 2, ui)
    assert ctrl.ctx.isr_mode == "orbit" and ctrl.is_open(orbit)


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
    open_isr_mode(t1, ui, "Hover")
    t1.click(t1.rings()[-1].nodes[0], 3, ui)
    open_isr_mode(t2, ui, "Orbit")
    t2.click(t2.rings()[-1].nodes[0], 3, ui)
    assert ui.offered[1] == ["I2", "I3", AssignIsrDroneNode.CANCEL]
    assert (t1.ctx.isr_drone, t2.ctx.isr_drone) == ("I1", "I3")


def test_cancel_isr_lock_clears_and_collapses() -> None:
    """Cancel in the dropdown clears mode and drone and closes the empty ring."""
    ctrl = make_controller()
    ui = FakeUI(choices=["I1", AssignIsrDroneNode.CANCEL])
    open_isr_mode(ctrl, ui, "Maintain")
    assign = ctrl.rings()[-1].nodes[0]
    ctrl.click(assign, 3, ui)
    ctrl.click(assign, 3, ui)
    assert ctrl.ctx.isr_mode is None and ctrl.ctx.isr_drone is None
    isr = child(ctrl.root, ctrl.ctx, "Lock ISR")
    assert ctrl.open_path == [ctrl.root, isr]
    assert ctrl.ctx.free_isr_drones() == ISR


def test_add_drone_grows_next_ring_and_dropdown_excludes_assigned() -> None:
    """Each add click adds one slot; a chosen drone is not offered to other slots."""
    ctrl = make_controller()
    ui = FakeUI(choices=["S2", "S1"])
    strike = child(ctrl.root, ctrl.ctx, "Set as strike")
    add = strike.children(ctrl.ctx)[0]
    assert isinstance(add, DynamicListNode)

    ctrl.click(ctrl.root, 0, ui)
    ctrl.click(strike, 1, ui)
    assert ctrl.click(add, 2, ui) is ClickResult.OPEN
    ctrl.click(add, 2, ui)
    slots = ctrl.rings()[-1].nodes
    assert len(slots) == 2 and all(isinstance(s, DroneSlotNode) for s in slots)
    assert add.children(ctrl.ctx) == slots  # cached, identical objects

    ctrl.click(slots[0], 3, ui)
    assert ui.offered[0][:-1] == ["S1", "S2", "S3"]
    assert ctrl.open_path[-1] is slots[0]  # vector ring opens after choosing
    assert ctrl.rings()[-1].nodes[0].label.startswith("Strike\nvector")

    ctrl.click(slots[1], 3, ui)
    assert ui.offered[1][:-1] == ["S1", "S3"]
    assert [a.drone_id for a in ctrl.ctx.strike_assignments] == ["S2", "S1"]


def test_removing_open_slot_prunes_path() -> None:
    """Removing a slot whose ring is open closes that ring."""
    ctrl = make_controller()
    ui = FakeUI(choices=["S1", DroneSlotNode.REMOVE])
    strike = child(ctrl.root, ctrl.ctx, "Set as strike")
    add = strike.children(ctrl.ctx)[0]
    ctrl.click(ctrl.root, 0, ui)
    ctrl.click(strike, 1, ui)
    ctrl.click(add, 2, ui)
    slot = add.children(ctrl.ctx)[0]
    ctrl.click(slot, 3, ui)
    assert ctrl.open_path[-1] is slot
    ctrl.click(slot, 3, ui)
    assert ctrl.ctx.strike_assignments == []
    assert ctrl.open_path[-1] is strike  # the now-empty slot ring collapses too


def test_to_dict_shape() -> None:
    """The exported dict has target, ISR and strike sections."""
    ctrl = make_controller()
    ctrl.ctx.isr_mode = "hover_hold"
    ctrl.ctx.isr_drone = "I1"
    ctrl.ctx.add_slot().drone_id = "S3"
    d = ctrl.ctx.to_dict()
    assert d["target"]["geo"] == {"lat": 1.0, "lon": 2.0}
    assert d["isr_lock"] == {"locked": True, "mode": "hover_hold", "drone_id": "I1"}
    assert d["strike"]["drones"] == [{"slot": 1, "drone_id": "S3", "vector": None}]


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

    view.select_target("T1")
    view.click_node(child(ctrl.root, ctrl.ctx, "Lock ISR"), 1)
    view.click_node(child(child(ctrl.root, ctrl.ctx, "Lock ISR"), ctrl.ctx, "Orbit"), 2)
    view.click_node(ctrl.rings()[-1].nodes[0], 3)  # Assign ISR drone -> ISR-02
    assert view.mission_dict()["targets"]["T1"]["isr_lock"]["drone_id"] == "ISR-02"
    out = radial_menu.OUTPUT_DIR
    out.mkdir(exist_ok=True)
    window.show()
    app.processEvents()
    assert window.grab().save(str(out / "screenshot_isr.png"))

    strike = child(ctrl.root, ctrl.ctx, "Set as strike")
    view.click_node(strike, 1)
    add = strike.children(ctrl.ctx)[0]
    view.click_node(add, 2)
    view.click_node(add, 2)
    slots = add.children(ctrl.ctx)
    view.click_node(slots[1], 3)
    view.click_node(slots[0], 3)

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
