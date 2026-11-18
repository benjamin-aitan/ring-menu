"""Hierarchical radial (ring) menu demo for ATR targets, built with PySide6.

Run with ``.venv/bin/python radial_menu.py``.

Tap an ATR bounding box to select it (the box changes colour) and open the
first ring of actions around it.  Each button opens the next ring
around it.  The right-hand panel shows the mission state as a nested dict
(JSON), which can be exported to ``outputs/``.
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from menu_model import (
    MenuController,
    MenuNode,
    MenuUI,
    MissionContext,
    RingStyle,
    Target,
    build_target_menu,
    polar_to_xy,
    ring_fan,
    ring_radii,
)

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "outputs"
#: Background "video feed"; regenerate with ``make_scenario.py``.
SCENARIO_IMAGE = HERE / "inputs" / "scenario.png"

SCENE_SIZE = (1200.0, 780.0)
STRIKE_DRONES = ["Strike-01", "Strike-02", "Strike-03", "Strike-04", "Strike-05"]
ISR_DRONES = ["ISR-01", "ISR-02", "ISR-03"]
DEMO_TARGETS = [
    Target("T1", "Tank", (380, 330, 96, 62), 34.052235, -118.243683, color="#d64545"),
    Target("T2", "Truck", (760, 500, 116, 64), 34.054120, -118.239870, color="#e0a030"),
    Target("T3", "APC", (900, 200, 92, 58), 34.056870, -118.236410, color="#c04fbf"),
]

COLORS = {
    "normal": "#3a3f4b",
    "hover": "#4d5466",
    "open": "#e0892f",
    "selected": "#2f7d6d",
    "text": "#f2f2f2",
    "bbox": "#4fd1ff",
}


class SegmentItem(QGraphicsPathItem):
    """One ring button: an annular wedge with an icon and label.

    :param node: Menu node the button represents.
    :param level: Ring number the button is in.
    :param center: Centre of the menu in scene coordinates.
    :param radii: ``(inner, outer)`` radius of the ring.
    :param angles: ``(start_deg, sweep_deg)`` of the wedge.
    :param state: ``"normal"``, ``"open"`` or ``"selected"``.
    :param text: Label text (may contain newlines).
    :param icon: Short glyph drawn above the label.
    """

    def __init__(
        self,
        node: MenuNode,
        level: int,
        center: QPointF,
        radii: Sequence[float],
        angles: Sequence[float],
        state: str,
        text: str,
        icon: str,
    ) -> None:
        """Build the wedge path and its label.

        :param node: Menu node the button represents.
        :type node: MenuNode
        :param level: Ring number the button is in.
        :type level: int
        :param center: Centre of the menu in scene coordinates.
        :type center: QPointF
        :param radii: ``(inner, outer)`` radius of the ring.
        :type radii: Sequence[float]
        :param angles: ``(start_deg, sweep_deg)`` of the wedge.
        :type angles: Sequence[float]
        :param state: ``"normal"``, ``"open"`` or ``"selected"``.
        :type state: str
        :param text: Label text.
        :type text: str
        :param icon: Short glyph drawn above the label.
        :type icon: str
        """
        r_in, r_out = radii
        start, sweep = angles
        super().__init__(segment_path(center, r_in, r_out, start, sweep))
        self.node = node
        self.level = level
        self.state = state
        self.setAcceptHoverEvents(True)
        self.setPen(QPen(QColor("#1d2027"), 1.0))
        self._apply_brush(hover=False)
        self.setZValue(10)
        self.setCursor(Qt.PointingHandCursor)

        r_mid = (r_in + r_out) / 2.0
        mid_x, mid_y = polar_to_xy(center.x(), center.y(), r_mid, start + sweep / 2.0)
        arc_len = math.pi * r_mid * sweep / 180.0
        width = max(58.0, min(arc_len, 118.0))
        # Keep a Python reference: otherwise PySide6 may delete the QObject-based child.
        self._label = label = QGraphicsTextItem(self)
        label.setDefaultTextColor(QColor(COLORS["text"]))
        label.setFont(QFont("Helvetica Neue", 9))
        label.document().setDefaultTextOption(QTextOption(Qt.AlignHCenter))
        label.setTextWidth(width)
        icon_html = f'<span style="font-size:15px">{icon}</span><br>' if icon else ""
        label.setHtml(icon_html + text.replace("\n", "<br>"))
        label.setAcceptedMouseButtons(Qt.NoButton)
        rect = label.boundingRect()
        label.setPos(mid_x - rect.width() / 2.0, mid_y - rect.height() / 2.0)

    def _apply_brush(self, hover: bool) -> None:
        """Fill the wedge according to its state and hover.

        :param hover: Whether the pointer is over the button.
        :type hover: bool
        """
        key = "hover" if hover and self.state == "normal" else self.state
        color = QColor(COLORS[key])
        if hover and self.state != "normal":
            color = color.lighter(115)
        self.setBrush(QBrush(color))

    def hoverEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Highlight on hover.

        :param event: Qt hover event.
        :type event: QGraphicsSceneHoverEvent
        """
        self._apply_brush(hover=True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Remove the hover highlight.

        :param event: Qt hover event.
        :type event: QGraphicsSceneHoverEvent
        """
        self._apply_brush(hover=False)
        super().hoverLeaveEvent(event)


class TargetItem(QGraphicsRectItem):
    """An ATR bounding box drawn on the video feed.

    :param target: The target to draw.
    """

    def __init__(self, target: Target) -> None:
        """Create the box and its class label.

        :param target: The target to draw.
        :type target: Target
        """
        x, y, w, h = target.rect
        super().__init__(x, y, w, h)
        self.target = target
        self.setZValue(5)
        self.setCursor(Qt.PointingHandCursor)
        label = QGraphicsSimpleTextItem(f"{target.target_id} {target.label}", self)
        label.setFont(QFont("Menlo", 10))
        label.setPos(x, y - 18)
        self._label = label
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        """Draw the box in the target's own colour when selected, cyan otherwise.

        :param active: Whether the target's menu is shown.
        :type active: bool
        """
        color = QColor(self.target.color if active else COLORS["bbox"])
        self.setPen(QPen(color, 3.0 if active else 1.5))
        fill = QColor(color)
        fill.setAlpha(60 if active else 28)
        self.setBrush(QBrush(fill))
        self._label.setBrush(QBrush(color))


def segment_path(center: QPointF, r_in: float, r_out: float, start_deg: float, sweep_deg: float) -> QPainterPath:
    """Build the outline of an annular wedge.

    :param center: Centre of the rings.
    :type center: QPointF
    :param r_in: Inner radius.
    :type r_in: float
    :param r_out: Outer radius.
    :type r_out: float
    :param start_deg: Start angle, counter-clockwise from 3 o'clock.
    :type start_deg: float
    :param sweep_deg: Angular width (positive, counter-clockwise).
    :type sweep_deg: float
    :returns: Closed wedge path.
    :rtype: QPainterPath
    """
    outer = QRectF(center.x() - r_out, center.y() - r_out, 2 * r_out, 2 * r_out)
    inner = QRectF(center.x() - r_in, center.y() - r_in, 2 * r_in, 2 * r_in)
    path = QPainterPath()
    path.arcMoveTo(outer, start_deg)
    path.arcTo(outer, start_deg, sweep_deg)
    path.arcTo(inner, start_deg + sweep_deg, -sweep_deg)
    path.closeSubpath()
    return path


class RadialMenuView(QGraphicsView, MenuUI):
    """Video-feed view with ATR boxes and the radial menu.

    :param targets: Targets to show.
    :param drones: Strike-drone roster shared by all targets.
    :param on_change: Called after every state change.
    :param on_message: Called with status messages.
    :param style: Ring layout sizes.
    :param isr_drones: ISR-drone roster shared by all targets.
    """

    def __init__(
        self,
        targets: Sequence[Target],
        drones: List[str],
        on_change: Callable[[], None],
        on_message: Callable[[str], None],
        style: RingStyle = RingStyle(),
        isr_drones: Sequence[str] = tuple(ISR_DRONES),
    ) -> None:
        """Create the scene, the target boxes and one menu per target.

        :param targets: Targets to show.
        :type targets: Sequence[Target]
        :param drones: Strike-drone roster shared by all targets.
        :type drones: list[str]
        :param on_change: Called after every state change.
        :type on_change: Callable[[], None]
        :param on_message: Called with status messages.
        :type on_message: Callable[[str], None]
        :param style: Ring layout sizes.
        :type style: RingStyle
        :param isr_drones: ISR-drone roster shared by all targets.
        :type isr_drones: Sequence[str]
        """
        super().__init__()
        self.scene_ = QGraphicsScene(0, 0, *SCENE_SIZE)
        self.setScene(self.scene_)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.style_ = style
        self._on_change = on_change
        self._on_message = on_message
        self._menu_items: List[QGraphicsItem] = []
        self.active_id: Optional[str] = None
        self._feed: Optional[QPixmap] = (
            QPixmap(str(SCENARIO_IMAGE)) if SCENARIO_IMAGE.exists() else None
        )

        self.targets: Dict[str, Target] = {t.target_id: t for t in targets}
        self.contexts: Dict[str, MissionContext] = {}
        self.controllers: Dict[str, MenuController] = {}
        self._target_items: Dict[str, TargetItem] = {}
        for t in targets:
            ctx = MissionContext(
                target=t, available_drones=drones, available_isr_drones=list(isr_drones)
            )
            ctx.drones_taken_elsewhere = self._taken_elsewhere_fn(t.target_id)
            self.contexts[t.target_id] = ctx
            self.controllers[t.target_id] = MenuController(build_target_menu(t), ctx)
            item = TargetItem(t)
            self.scene_.addItem(item)
            self._target_items[t.target_id] = item

    def _taken_elsewhere_fn(self, target_id: str) -> Callable[[str], List[str]]:
        """Make a callback listing drones assigned to targets other than one.

        :param target_id: Target to exclude.
        :type target_id: str
        :returns: Callback ``taken(kind)`` returning drone identifiers, where
            ``kind`` is ``"strike"`` or ``"isr"``.
        :rtype: Callable[[str], list[str]]
        """

        def taken(kind: str) -> List[str]:
            """List drones of one kind assigned to other targets.

            :param kind: ``"strike"`` or ``"isr"``.
            :type kind: str
            :returns: Drone identifiers.
            :rtype: list[str]
            """
            if kind == "isr":
                return [
                    ctx.isr_drone
                    for tid, ctx in self.contexts.items()
                    if tid != target_id and ctx.isr_drone
                ]
            return [
                a.drone_id
                for tid, ctx in self.contexts.items()
                if tid != target_id
                for a in ctx.strike_assignments
                if a.drone_id
            ]

        return taken

    # -- MenuUI ---------------------------------------------------------------

    def choose_from_list(
        self, node: MenuNode, options: Sequence[str], current: Optional[str]
    ) -> Optional[str]:
        """Show a dropdown at the pointer and return the chosen option.

        :param node: Node requesting the choice.
        :type node: MenuNode
        :param options: Options to offer.
        :type options: Sequence[str]
        :param current: Currently chosen option, shown checked.
        :type current: str or None
        :returns: Chosen option, or ``None`` if dismissed.
        :rtype: str or None
        """
        menu = QMenu(self)
        if not any(o for o in options if not o.startswith("✕")):
            empty = menu.addAction("No drones available")
            empty.setEnabled(False)
        for option in options:
            if option.startswith("✕"):
                menu.addSeparator()
            action = menu.addAction(option)
            action.setCheckable(True)
            action.setChecked(option == current)
        chosen = menu.exec(QCursor.pos())
        return chosen.text() if chosen is not None else None

    def ask_number(
        self, title: str, current: float, minimum: float, maximum: float
    ) -> Optional[float]:
        """Ask for a number in a dialog.

        :param title: Prompt shown to the operator.
        :type title: str
        :param current: Pre-filled value.
        :type current: float
        :param minimum: Smallest accepted value.
        :type minimum: float
        :param maximum: Largest accepted value.
        :type maximum: float
        :returns: Entered value, or ``None`` if cancelled.
        :rtype: float or None
        """
        value, ok = QInputDialog.getDouble(
            self, "Strike timing", title, current, minimum, maximum, 1
        )
        return value if ok else None

    def show_message(self, text: str, modal: bool = False) -> None:
        """Show a status line, or a dialog if ``modal`` is set.

        :param text: Message text.
        :type text: str
        :param modal: Show a blocking dialog.
        :type modal: bool
        """
        if modal:
            QMessageBox.information(self, "Target", text)
        self._on_message(text.splitlines()[0])

    # -- drawing --------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Scale the whole feed to fit the view, keeping its aspect ratio.

        :param event: Qt resize event.
        :type event: QResizeEvent
        """
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802 (Qt naming)
        """Draw the scenario image as the ISR feed, or a dark grid if it is missing.

        :param painter: Scene painter.
        :type painter: QPainter
        :param rect: Exposed area.
        :type rect: QRectF
        """
        if self._feed is not None:
            painter.fillRect(rect, QColor("#15191c"))  # letterbox bars outside the feed
            painter.drawPixmap(self.sceneRect(), self._feed, QRectF(self._feed.rect()))
            return
        gradient = QLinearGradient(0, 0, SCENE_SIZE[0], SCENE_SIZE[1])
        gradient.setColorAt(0.0, QColor("#2b3a2f"))
        gradient.setColorAt(1.0, QColor("#1c2420"))
        painter.fillRect(rect, gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        step = 50
        x = int(rect.left()) - int(rect.left()) % step
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += step
        y = int(rect.top()) - int(rect.top()) % step
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += step

    def rebuild(self) -> None:
        """Redraw the menu from the active controller's open rings."""
        for item in self._menu_items:
            self.scene_.removeItem(item)
        self._menu_items = []
        for tid, item in self._target_items.items():
            item.set_active(tid == self.active_id)

        if self.active_id is not None:
            ctrl = self.controllers[self.active_id]
            target = self.targets[self.active_id]
            cx, cy = target.center()
            center = QPointF(cx, cy)
            # Start ring 1 just outside the bounding box corners.
            _, _, w, h = target.rect
            style = dataclasses.replace(
                self.style_,
                center_radius=max(self.style_.center_radius, math.hypot(w, h) / 2.0 + 4.0),
            )
            fan_center = 90.0
            for ring in ctrl.rings():
                radii = ring_radii(ring.level, style)
                layout = ring_fan(len(ring.nodes), ring.level, fan_center, style)
                next_center = fan_center
                for node, angles in zip(ring.nodes, layout):
                    if ctrl.is_open(node):
                        state = "open"
                        next_center = angles[0] + angles[1] / 2.0
                    elif node.is_selected(ctrl.ctx):
                        state = "selected"
                    else:
                        state = "normal"
                    seg = SegmentItem(
                        node, ring.level, center, radii, angles, state,
                        node.display_label(ctrl.ctx), node.icon,
                    )
                    self.scene_.addItem(seg)
                    self._menu_items.append(seg)
                fan_center = next_center
        self._on_change()

    # -- input ----------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Route a left click to the menu, a target box, or close the menu.

        :param event: Qt mouse event.
        :type event: QMouseEvent
        """
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.position().toPoint())
        while item is not None and not isinstance(item, (SegmentItem, TargetItem)):
            item = item.parentItem()

        if isinstance(item, SegmentItem):
            self.click_node(item.node, item.level)
        elif isinstance(item, TargetItem):
            self.select_target(item.target.target_id)
        else:
            self.select_target(None)

    def click_node(self, node: MenuNode, level: int) -> None:
        """Click a menu button of the active target and redraw.

        :param node: Clicked node.
        :type node: MenuNode
        :param level: Ring the node is in (1 for the innermost ring).
        :type level: int
        """
        if self.active_id is None:
            return
        self.controllers[self.active_id].click(node, level, self)
        self.rebuild()

    def select_target(self, target_id: Optional[str]) -> None:
        """Select a target and open its first ring, or close the menu.

        Tapping the already-selected target closes its menu.  Mission state
        (ISR mode, drone slots) is kept; only the open rings reset.

        :param target_id: Target to select, or ``None`` to close the menu.
        :type target_id: str or None
        """
        if target_id is None or target_id == self.active_id:
            self.active_id = None
        else:
            self.active_id = target_id
            ctrl = self.controllers[target_id]
            ctrl.open_path = [ctrl.root]
        self.rebuild()

    def mission_dict(self) -> dict:
        """Return the state of all targets as one nested dict.

        :returns: ``{"strike_drones": [...], "isr_drones": [...], "targets": {id: ctx_dict}}``.
        :rtype: dict
        """
        return {
            "strike_drones": list(STRIKE_DRONES),
            "isr_drones": list(ISR_DRONES),
            "targets": {tid: ctx.to_dict() for tid, ctx in self.contexts.items()},
        }


class MainWindow(QMainWindow):
    """Main window: menu view on the left, mission JSON on the right."""

    def __init__(self) -> None:
        """Build the window layout."""
        super().__init__()
        self.setWindowTitle("TALON ring menu prototype")
        self.view = RadialMenuView(
            DEMO_TARGETS, STRIKE_DRONES, on_change=self._refresh_json, on_message=self._message
        )

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Mission state (nested dict)"))
        self.json_box = QPlainTextEdit()
        self.json_box.setReadOnly(True)
        self.json_box.setFont(QFont("Menlo", 10))
        layout.addWidget(self.json_box)
        buttons = QHBoxLayout()
        export = QPushButton("Export JSON")
        export.clicked.connect(self._export)
        buttons.addWidget(export)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        splitter = QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(panel)
        splitter.setSizes([1100, 380])
        self.setCentralWidget(splitter)
        self.resize(1500, 940)
        self.statusBar().showMessage("Click an ATR bounding box to start.")
        self.view.rebuild()

    def _refresh_json(self) -> None:
        """Show the current mission dict in the side panel."""
        self.json_box.setPlainText(json.dumps(self.view.mission_dict(), indent=2))

    def _message(self, text: str) -> None:
        """Show a status-bar message.

        :param text: Message text.
        :type text: str
        """
        self.statusBar().showMessage(text, 6000)

    def _export(self) -> None:
        """Write the mission dict to a timestamped file in ``outputs/``."""
        OUTPUT_DIR.mkdir(exist_ok=True)
        path = OUTPUT_DIR / f"mission_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps(self.view.mission_dict(), indent=2))
        self._message(f"Exported {path.relative_to(HERE)}")


def main() -> int:
    """Start the demo application.

    :returns: Qt exit code.
    :rtype: int
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
