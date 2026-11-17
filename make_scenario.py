"""Render a simple cartoon ISR scene with the demo targets (tank, truck, APC).

The scene is seen from an oblique drone viewpoint: a horizon near the top,
a ground plane, a road running towards a vanishing point, and trees and
buildings that shrink with distance.  Each vehicle is drawn inside its
target's ATR bounding box from ``radial_menu.DEMO_TARGETS``, so the boxes in
the menu demo line up with the vehicles.

Run with ``.venv/bin/python make_scenario.py``; writes ``inputs/scenario.png``.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Callable, Dict, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)

from menu_model import Target

HERE = Path(__file__).resolve().parent
SCENARIO_PATH = HERE / "inputs" / "scenario.png"

HORIZON_Y = 90.0
VANISHING_POINT = (760.0, HORIZON_Y)
ROAD_BOTTOM = (560.0, 360.0)  # centre x and width at the bottom edge

Pt = Tuple[float, float]


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


def _poly(painter: QPainter, points: Sequence[Pt], color: str, outline: str = "#1e2418") -> None:
    """Fill a polygon with a thin dark outline.

    :param painter: Active painter.
    :type painter: QPainter
    :param points: Polygon vertices.
    :type points: Sequence[tuple[float, float]]
    :param color: Fill colour.
    :type color: str
    :param outline: Outline colour.
    :type outline: str
    """
    painter.setPen(QPen(QColor(outline), 1.0))
    painter.setBrush(QBrush(QColor(color)))
    painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


def _ellipse(painter: QPainter, cx: float, cy: float, rx: float, ry: float, color: QColor) -> None:
    """Fill an ellipse without an outline.

    :param painter: Active painter.
    :type painter: QPainter
    :param cx: Centre x.
    :type cx: float
    :param cy: Centre y.
    :type cy: float
    :param rx: Horizontal radius.
    :type rx: float
    :param ry: Vertical radius.
    :type ry: float
    :param color: Fill colour.
    :type color: QColor
    """
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawEllipse(QPointF(cx, cy), rx, ry)


def _shadow(painter: QPainter, cx: float, cy: float, rx: float, ry: float) -> None:
    """Draw a soft ground shadow.

    :param painter: Active painter.
    :type painter: QPainter
    :param cx: Centre x.
    :type cx: float
    :param cy: Centre y.
    :type cy: float
    :param rx: Horizontal radius.
    :type rx: float
    :param ry: Vertical radius.
    :type ry: float
    """
    _ellipse(painter, cx, cy, rx, ry, QColor(0, 0, 0, 70))


def oblique_box(
    painter: QPainter,
    x: float,
    y: float,
    w: float,
    h: float,
    ox: float,
    oy: float,
    colors: Tuple[str, str, str],
) -> None:
    """Draw a box in oblique projection: side face, top face and right end face.

    The side face is the rectangle ``(x, y, w, h)``.  The top and end faces
    recede up and to the right by ``(ox, -oy)``.

    :param painter: Active painter.
    :type painter: QPainter
    :param x: Left of the side face.
    :type x: float
    :param y: Top of the side face.
    :type y: float
    :param w: Width of the side face.
    :type w: float
    :param h: Height of the side face.
    :type h: float
    :param ox: Horizontal depth offset.
    :type ox: float
    :param oy: Vertical depth offset (upwards).
    :type oy: float
    :param colors: ``(top, side, end)`` fill colours.
    :type colors: tuple[str, str, str]
    """
    top, side, end = colors
    _poly(painter, [(x, y), (x + w, y), (x + w + ox, y - oy), (x + ox, y - oy)], top)
    _poly(painter, [(x + w, y), (x + w, y + h), (x + w + ox, y + h - oy), (x + w + ox, y - oy)], end)
    _poly(painter, [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], side)


def _wheel(painter: QPainter, cx: float, cy: float, r: float) -> None:
    """Draw a wheel with a hub.

    :param painter: Active painter.
    :type painter: QPainter
    :param cx: Centre x.
    :type cx: float
    :param cy: Centre y.
    :type cy: float
    :param r: Radius.
    :type r: float
    """
    painter.setPen(QPen(QColor("#111"), 1.0))
    painter.setBrush(QBrush(QColor("#2a2a28")))
    painter.drawEllipse(QPointF(cx, cy), r, r * 0.9)
    _ellipse(painter, cx, cy, r * 0.4, r * 0.36, QColor("#6b6b60"))


def _area(rect: Tuple[float, float, float, float], margin: float = 5.0) -> Tuple[float, float, float, float]:
    """Shrink a bounding box by a margin.

    :param rect: ``(x, y, w, h)`` bounding box.
    :type rect: tuple[float, float, float, float]
    :param margin: Margin on every side.
    :type margin: float
    :returns: ``(left, bottom, width, height)`` of the drawable area.
    :rtype: tuple[float, float, float, float]
    """
    x, y, w, h = rect
    return x + margin, y + h - margin, w - 2 * margin, h - 2 * margin


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------


def draw_tank(painter: QPainter, rect: Tuple[float, float, float, float]) -> None:
    """Draw a cartoon tank in 3/4 view inside a bounding box.

    :param painter: Active painter.
    :type painter: QPainter
    :param rect: ``(x, y, w, h)`` bounding box.
    :type rect: tuple[float, float, float, float]
    """
    left, bottom, w, h = _area(rect)
    ox, oy = 0.2 * w, 0.36 * h
    sw = w - ox
    _shadow(painter, left + w / 2, bottom - 0.12 * h, w * 0.56, h * 0.22)
    # Tracks.
    track_h = 0.28 * h
    oblique_box(painter, left, bottom - track_h, sw, track_h, ox, oy * 0.5, ("#2f3127", "#26281f", "#1f2119"))
    for i in range(6):
        _wheel(painter, left + sw * (0.1 + 0.16 * i), bottom - track_h / 2, track_h * 0.36)
    # Hull.
    hull_y = bottom - track_h - 0.2 * h
    oblique_box(painter, left - 0.02 * w, hull_y, sw + 0.02 * w, 0.2 * h, ox, oy, ("#8a9358", "#5e6a36", "#4a542a"))
    # Turret and barrel.
    cx, cy = left + sw / 2 + ox / 2, hull_y - oy / 2
    painter.setPen(QPen(QColor("#2c3220"), 4.0, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(cx + 0.08 * w, cy - 0.06 * h), QPointF(left + w - 1, cy - 0.16 * h))
    painter.setPen(QPen(QColor("#1e2418"), 1.0))
    painter.setBrush(QBrush(QColor("#59652f")))
    painter.drawRoundedRect(QRectF(cx - 0.18 * w, cy - 0.16 * h, 0.36 * w, 0.2 * h), 6, 6)
    _ellipse(painter, cx, cy - 0.16 * h, 0.17 * w, 0.09 * h, QColor("#949d62"))


def draw_truck(painter: QPainter, rect: Tuple[float, float, float, float]) -> None:
    """Draw a cartoon cargo truck in 3/4 view inside a bounding box.

    :param painter: Active painter.
    :type painter: QPainter
    :param rect: ``(x, y, w, h)`` bounding box.
    :type rect: tuple[float, float, float, float]
    """
    left, bottom, w, h = _area(rect)
    ox, oy = 0.16 * w, 0.32 * h
    sw = w - ox
    _shadow(painter, left + w / 2, bottom - 0.1 * h, w * 0.55, h * 0.2)
    chassis_y = bottom - 0.24 * h
    oblique_box(painter, left, chassis_y, sw, 0.08 * h, ox, oy * 0.6, ("#2b2b25", "#22221d", "#1a1a16"))
    for fx in (0.14, 0.3, 0.84):
        _wheel(painter, left + sw * fx, bottom - 0.12 * h, 0.13 * h)
    # Canvas-covered cargo box (rear) and cab (front, facing right).
    cargo_h = 0.44 * h
    oblique_box(painter, left, chassis_y - cargo_h, 0.66 * sw, cargo_h, ox, oy, ("#c7b88a", "#a8996b", "#8c7f56"))
    painter.setPen(QPen(QColor(80, 70, 45, 160), 1.0))
    for fx in (0.22, 0.44):
        x = left + 0.66 * sw * fx * 2
        painter.drawLine(QPointF(x, chassis_y - cargo_h), QPointF(x, chassis_y))
    cab_x, cab_h = left + 0.7 * sw, 0.34 * h
    cab_w = 0.3 * sw
    oblique_box(painter, cab_x, chassis_y - cab_h, cab_w, cab_h, ox, oy, ("#7f8a4e", "#5e6a36", "#4a542a"))
    # Windshield on the cab's end face, side window on the side face.
    ex, ey = cab_x + cab_w, chassis_y - cab_h
    _poly(
        painter,
        [(ex + 2, ey + 3), (ex + ox - 2, ey - oy + 4), (ex + ox - 2, ey - oy + cab_h * 0.45), (ex + 2, ey + cab_h * 0.5)],
        "#7f98a8",
    )
    _poly(
        painter,
        [(cab_x + 3, ey + 3), (cab_x + cab_w * 0.7, ey + 3), (cab_x + cab_w * 0.7, ey + cab_h * 0.45), (cab_x + 3, ey + cab_h * 0.45)],
        "#6d8494",
    )


def draw_apc(painter: QPainter, rect: Tuple[float, float, float, float]) -> None:
    """Draw a cartoon wheeled APC in 3/4 view inside a bounding box.

    :param painter: Active painter.
    :type painter: QPainter
    :param rect: ``(x, y, w, h)`` bounding box.
    :type rect: tuple[float, float, float, float]
    """
    left, bottom, w, h = _area(rect)
    ox, oy = 0.18 * w, 0.32 * h
    sw = w - ox
    _shadow(painter, left + w / 2, bottom - 0.1 * h, w * 0.55, h * 0.2)
    for fx in (0.13, 0.36, 0.62, 0.86):
        _wheel(painter, left + sw * fx, bottom - 0.14 * h, 0.15 * h)
    yb = bottom - 0.16 * h
    hh = 0.4 * h
    yt = yb - hh
    xs = left + 0.78 * sw  # where the sloped glacis starts
    xe = left + sw
    ym = yt + 0.5 * hh
    top, side, end, glacis = "#b3a16e", "#8b7b4c", "#6f623c", "#9d8c5a"
    _poly(painter, [(left, yt), (xs, yt), (xs + ox, yt - oy), (left + ox, yt - oy)], top)
    _poly(painter, [(xs, yt), (xe, ym), (xe + ox, ym - oy), (xs + ox, yt - oy)], glacis)
    _poly(painter, [(xe, ym), (xe, yb), (xe + ox, yb - oy), (xe + ox, ym - oy)], end)
    _poly(painter, [(left, yt), (xs, yt), (xe, ym), (xe, yb), (left, yb)], side)
    # Small turret with a short gun.
    cx, cy = left + 0.42 * sw + ox / 2, yt - oy / 2
    painter.setPen(QPen(QColor("#2e2a1c"), 3.0, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(cx + 0.06 * w, cy - 0.08 * h), QPointF(cx + 0.36 * w, cy - 0.14 * h))
    painter.setPen(QPen(QColor("#1e2418"), 1.0))
    painter.setBrush(QBrush(QColor("#7d6f45")))
    painter.drawRoundedRect(QRectF(cx - 0.12 * w, cy - 0.14 * h, 0.24 * w, 0.16 * h), 4, 4)
    _ellipse(painter, cx, cy - 0.14 * h, 0.11 * w, 0.06 * h, QColor("#c0af7c"))


VEHICLE_DRAWERS: Dict[str, Callable[[QPainter, Tuple[float, float, float, float]], None]] = {
    "Tank": draw_tank,
    "Truck": draw_truck,
    "APC": draw_apc,
}


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def depth_scale(y: float, height: float) -> float:
    """Return a size factor for an object whose base is at screen ``y``.

    :param y: Screen y of the object's base.
    :type y: float
    :param height: Image height.
    :type height: float
    :returns: About 0.25 at the horizon, 1.0 at the bottom edge.
    :rtype: float
    """
    t = max(0.0, (y - HORIZON_Y) / (height - HORIZON_Y))
    return 0.25 + 0.75 * t


def road_edges(y: float, height: float) -> Tuple[float, float]:
    """Return the left and right road edge at screen ``y``.

    :param y: Screen y.
    :type y: float
    :param height: Image height.
    :type height: float
    :returns: ``(left_x, right_x)``.
    :rtype: tuple[float, float]
    """
    t = (y - HORIZON_Y) / (height - HORIZON_Y)
    vx, _ = VANISHING_POINT
    cx = vx + (ROAD_BOTTOM[0] - vx) * t
    half = ROAD_BOTTOM[1] * t / 2.0
    return cx - half, cx + half


def draw_ground(painter: QPainter, width: float, height: float) -> None:
    """Draw sky, ground, field rows, speckle texture and the road.

    :param painter: Active painter.
    :type painter: QPainter
    :param width: Image width.
    :type width: float
    :param height: Image height.
    :type height: float
    """
    sky = QLinearGradient(0, 0, 0, HORIZON_Y)
    sky.setColorAt(0.0, QColor("#8fb3cc"))
    sky.setColorAt(1.0, QColor("#d5dfd9"))
    painter.fillRect(QRectF(0, 0, width, HORIZON_Y), sky)
    ground = QLinearGradient(0, HORIZON_Y, 0, height)
    ground.setColorAt(0.0, QColor("#a9ad8a"))
    ground.setColorAt(0.25, QColor("#86915e"))
    ground.setColorAt(1.0, QColor("#5d6b3a"))
    painter.fillRect(QRectF(0, HORIZON_Y, width, height - HORIZON_Y), ground)

    # Distant tree line on the horizon.
    rng = random.Random(7)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#5f6f4a")))
    x = 0.0
    while x < width:
        r = rng.uniform(6, 14)
        painter.drawEllipse(QPointF(x, HORIZON_Y - r * 0.3), r * 1.4, r)
        x += r * 1.6

    # Field furrows converging on the vanishing point.
    vx, vy = VANISHING_POINT
    painter.setPen(QPen(QColor(60, 70, 35, 30), 1.0))
    for bx in range(-1600, int(width) + 1600, 160):
        painter.drawLine(QPointF(vx, vy), QPointF(bx, height))
    # Horizontal field boundaries, spaced closer towards the horizon.
    painter.setPen(QPen(QColor(50, 60, 30, 60), 1.0))
    for i in range(1, 12):
        t = (i / 12.0) ** 1.8
        y = HORIZON_Y + t * (height - HORIZON_Y)
        painter.drawLine(QPointF(0, y), QPointF(width, y))

    # Speckle texture (grass tufts / stones), smaller with distance.
    for _ in range(1600):
        y = rng.uniform(HORIZON_Y + 4, height)
        s = depth_scale(y, height)
        x = rng.uniform(0, width)
        shade = rng.choice([QColor(40, 55, 25, 70), QColor(150, 150, 110, 60)])
        _ellipse(painter, x, y, 2.2 * s, 1.1 * s, shade)

    # Dirt road.
    left_bottom, right_bottom = road_edges(height, height)
    _poly(painter, [VANISHING_POINT, (right_bottom, height), (left_bottom, height)], "#a8946a", "#8c7a55")
    painter.setPen(QPen(QColor(110, 95, 65, 140), 2.0, Qt.DashLine))
    painter.drawLine(QPointF(vx, vy), QPointF((left_bottom + right_bottom) / 2.0, height))
    for _ in range(400):
        y = rng.uniform(HORIZON_Y + 10, height)
        lx, rx = road_edges(y, height)
        s = depth_scale(y, height)
        _ellipse(painter, rng.uniform(lx, rx), y, 2.0 * s, 1.0 * s, QColor(90, 75, 50, 70))


def draw_tree(painter: QPainter, x: float, y: float, s: float) -> None:
    """Draw a cartoon tree whose trunk base is at ``(x, y)``.

    :param painter: Active painter.
    :type painter: QPainter
    :param x: Base x.
    :type x: float
    :param y: Base y.
    :type y: float
    :param s: Size factor from :func:`depth_scale`.
    :type s: float
    """
    _shadow(painter, x + 10 * s, y, 26 * s, 8 * s)
    painter.setPen(QPen(QColor("#2b2116"), 1.0))
    painter.setBrush(QBrush(QColor("#5a4028")))
    painter.drawRect(QRectF(x - 3 * s, y - 22 * s, 6 * s, 22 * s))
    for dx, dy, r, color in (
        (-10, -34, 16, "#2f4a24"),
        (10, -36, 15, "#2f4a24"),
        (0, -48, 18, "#3c5c2c"),
        (-4, -52, 9, "#58783e"),
    ):
        painter.setPen(QPen(QColor("#1f3018"), 1.0))
        painter.setBrush(QBrush(QColor(color)))
        painter.drawEllipse(QPointF(x + dx * s, y + dy * s), r * s, r * 0.85 * s)


def draw_building(painter: QPainter, x: float, y: float, s: float) -> None:
    """Draw a simple flat-roofed building whose front-left base is at ``(x, y)``.

    :param painter: Active painter.
    :type painter: QPainter
    :param x: Base x of the front face.
    :type x: float
    :param y: Base y of the front face.
    :type y: float
    :param s: Size factor from :func:`depth_scale`.
    :type s: float
    """
    w, h, ox, oy = 90 * s, 46 * s, 34 * s, 26 * s
    _shadow(painter, x + w / 2 + ox, y - oy / 3, w * 0.75, 14 * s)
    oblique_box(painter, x, y - h, w, h, ox, oy, ("#b8ab95", "#d2c7b0", "#9c907b"))
    painter.setPen(QPen(QColor("#3a3a3a"), 1.0))
    painter.setBrush(QBrush(QColor("#4c5560")))
    for i in range(3):
        painter.drawRect(QRectF(x + (12 + i * 26) * s, y - h + 12 * s, 12 * s, 12 * s))
    painter.setBrush(QBrush(QColor("#5a4028")))
    painter.drawRect(QRectF(x + w - 20 * s, y - 22 * s, 11 * s, 22 * s))


def render_scenario(targets: Sequence[Target], size: Tuple[float, float]) -> QImage:
    """Render the scene with each target's vehicle inside its bounding box.

    :param targets: Targets whose ``label`` selects the vehicle drawer.
    :type targets: Sequence[Target]
    :param size: ``(width, height)`` of the image in pixels.
    :type size: tuple[float, float]
    :returns: The rendered image.
    :rtype: QImage
    :raises KeyError: If a target label has no vehicle drawer.
    """
    width, height = size
    image = QImage(int(width), int(height), QImage.Format_ARGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    draw_ground(painter, width, height)

    scenery = [
        ("building", 470, 128), ("building", 560, 122), ("building", 150, 420),
        ("tree", 300, 160), ("tree", 640, 170), ("tree", 1130, 175), ("tree", 1050, 300),
        ("tree", 110, 250), ("tree", 240, 330), ("tree", 560, 420), ("tree", 1100, 470),
        ("tree", 90, 640), ("tree", 330, 720), ("tree", 1050, 720), ("tree", 980, 610),
    ]
    vehicles = [(t.rect[1] + t.rect[3], "vehicle", t) for t in targets]
    items = [(y, kind, (x, y)) for kind, x, y in scenery] + vehicles
    # Painter's algorithm: draw from far (top) to near (bottom).
    for y, kind, payload in sorted(items, key=lambda item: item[0]):
        if kind == "tree":
            draw_tree(painter, payload[0], y, depth_scale(y, height))
        elif kind == "building":
            draw_building(painter, payload[0], y, depth_scale(y, height))
        else:
            VEHICLE_DRAWERS[payload.label](painter, payload.rect)
    painter.end()
    return image


def main() -> int:
    """Render the demo scene to ``inputs/scenario.png``.

    :returns: Process exit code.
    :rtype: int
    """
    from radial_menu import DEMO_TARGETS, SCENE_SIZE

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841 (keeps Qt alive)
    SCENARIO_PATH.parent.mkdir(exist_ok=True)
    image = render_scenario(DEMO_TARGETS, SCENE_SIZE)
    if not image.save(str(SCENARIO_PATH)):
        print(f"Failed to write {SCENARIO_PATH}", file=sys.stderr)
        return 1
    print(f"Wrote {SCENARIO_PATH.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
