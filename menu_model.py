"""Toolkit-independent model for the hierarchical radial (ring) menu.

This module has no Qt dependency so it can be unit-tested headlessly.  It
contains:

* the mission state (:class:`MissionContext`) that menu actions mutate and that
  can be exported as a nested ``dict``;
* the menu node class hierarchy, where each class defines how its children
  behave when clicked;
* :class:`MenuController`, which tracks which rings are open;
* pure ring-layout geometry helpers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Mission state
# ---------------------------------------------------------------------------


@dataclass
class Target:
    """An ATR-detected target with a bounding box in scene coordinates.

    :param target_id: Unique target identifier, e.g. ``"T1"``.
    :param label: ATR class label, e.g. ``"Tank"``.
    :param rect: Bounding box as ``(x, y, width, height)`` in scene pixels.
    :param lat: Mock latitude of the target in degrees.
    :param lon: Mock longitude of the target in degrees.
    :param color: Colour of the root circle shown for this target.
    """

    target_id: str
    label: str
    rect: Tuple[float, float, float, float]
    lat: float
    lon: float
    color: str = "#d64545"

    def center(self) -> Tuple[float, float]:
        """Return the centre of the bounding box.

        :returns: ``(x, y)`` centre in scene pixels.
        :rtype: tuple[float, float]
        """
        x, y, w, h = self.rect
        return x + w / 2.0, y + h / 2.0


#: Default gap, in seconds, between one strike and the next in a sequence.
DEFAULT_STRIKE_DELAY_S = 10.0
#: Longest delay the operator may configure, in seconds.
MAX_STRIKE_DELAY_S = 600.0


@dataclass
class DroneAssignment:
    """One strike-drone slot in a strike tasking.

    Slots strike in list order: the first at T+0, each later one ``delay_s``
    seconds after the slot before it.  ``delay_s`` of the first slot is unused.

    :param slot_id: Stable identifier of the slot within its mission.
    :param drone_id: Selected strike drone, or ``None`` if not chosen yet.
    :param vector: Strike vector (not implemented yet), or ``None``.
    :param delay_s: Seconds after the previous slot's strike; ``0`` is simultaneous.
    """

    slot_id: int
    drone_id: Optional[str] = None
    vector: Optional[dict] = None
    delay_s: float = DEFAULT_STRIKE_DELAY_S


@dataclass
class MissionContext:
    """Runtime state for one target, mutated by menu actions.

    :param target: The target this context belongs to.
    :param available_drones: Shared list of strike drones that can be assigned.
    :param available_isr_drones: Shared list of ISR drones that can be assigned.
    :param isr_mode: Selected ISR lock behaviour, or ``None`` if not locked.
    :param isr_drone: ISR drone tasked with the lock, or ``None``.
    :param is_strike_target: Whether the target is designated for strike.
    :param strike_assignments: Strike-drone slots added by the operator.
    """

    target: Target
    available_drones: List[str]
    available_isr_drones: List[str] = field(default_factory=list)
    isr_mode: Optional[str] = None
    isr_drone: Optional[str] = None
    is_strike_target: bool = False
    strike_assignments: List[DroneAssignment] = field(default_factory=list)
    _next_slot_id: int = 1
    #: ``drones_taken_elsewhere(kind)`` lists drones of ``kind`` (``"strike"`` or
    #: ``"isr"``) tasked on *other* targets; set by the owner of all contexts.
    drones_taken_elsewhere: Callable[[str], List[str]] = field(default=lambda kind: [], repr=False)

    def free_isr_drones(self) -> List[str]:
        """List ISR drones not tasked on any other target.

        The drone already locked on this target is kept in the list.

        :returns: Selectable ISR drone identifiers, in roster order.
        :rtype: list[str]
        """
        taken = set(self.drones_taken_elsewhere("isr"))
        return [d for d in self.available_isr_drones if d not in taken]

    def cancel_isr_lock(self) -> None:
        """Clear the ISR lock mode and release its drone."""
        self.isr_mode = None
        self.isr_drone = None

    def add_slot(self) -> DroneAssignment:
        """Append a new, empty strike-drone slot.

        :returns: The newly created slot.
        :rtype: DroneAssignment
        """
        slot = DroneAssignment(slot_id=self._next_slot_id)
        self._next_slot_id += 1
        self.strike_assignments.append(slot)
        return slot

    def remove_slot(self, slot_id: int) -> None:
        """Remove a strike-drone slot, if present.

        :param slot_id: Identifier of the slot to remove.
        :type slot_id: int
        """
        self.strike_assignments = [a for a in self.strike_assignments if a.slot_id != slot_id]

    def slot(self, slot_id: int) -> Optional[DroneAssignment]:
        """Look up a slot by identifier.

        :param slot_id: Identifier of the slot.
        :type slot_id: int
        :returns: The slot, or ``None`` if it no longer exists.
        :rtype: DroneAssignment or None
        """
        for assignment in self.strike_assignments:
            if assignment.slot_id == slot_id:
                return assignment
        return None

    def is_first_slot(self, slot_id: int) -> bool:
        """Return whether a slot is the first strike in the sequence.

        :param slot_id: Identifier of the slot.
        :type slot_id: int
        :returns: ``True`` if it is the first slot.
        :rtype: bool
        """
        return bool(self.strike_assignments) and self.strike_assignments[0].slot_id == slot_id

    def strike_offsets(self) -> Dict[int, float]:
        """Compute each slot's strike time relative to the first strike.

        :returns: Slot id mapped to seconds after the first strike (first is 0).
        :rtype: dict[int, float]
        """
        offsets: Dict[int, float] = {}
        t = 0.0
        for i, a in enumerate(self.strike_assignments):
            if i > 0:
                t += a.delay_s
            offsets[a.slot_id] = t
        return offsets

    def free_drones(self, for_slot_id: Optional[int] = None) -> List[str]:
        """List drones that may be chosen for a slot.

        A drone is free if no other slot (in this or any other mission context)
        has it.  The drone already in ``for_slot_id`` is kept in the list.

        :param for_slot_id: Slot the choice is for, so its own drone is kept.
        :type for_slot_id: int or None
        :returns: Selectable drone identifiers, in roster order.
        :rtype: list[str]
        """
        taken = {
            a.drone_id
            for a in self.strike_assignments
            if a.drone_id is not None and a.slot_id != for_slot_id
        }
        taken.update(self.drones_taken_elsewhere("strike"))
        return [d for d in self.available_drones if d not in taken]

    def to_dict(self) -> dict:
        """Export the mission state as a JSON-serialisable nested dict.

        :returns: Nested dict describing the target and its tasking.
        :rtype: dict
        """
        x, y, w, h = self.target.rect
        offsets = self.strike_offsets()
        return {
            "target": {
                "id": self.target.target_id,
                "label": self.target.label,
                "bbox": {"x": x, "y": y, "w": w, "h": h},
                "geo": {"lat": self.target.lat, "lon": self.target.lon},
            },
            "isr_lock": {
                "locked": self.isr_mode is not None,
                "mode": self.isr_mode,
                "drone_id": self.isr_drone,
            },
            "strike": {
                "is_strike_target": self.is_strike_target,
                "drones": [
                    {
                        "slot": a.slot_id,
                        "drone_id": a.drone_id,
                        "vector": a.vector,
                        "delay_after_previous_s": None if self.is_first_slot(a.slot_id) else a.delay_s,
                        "strike_offset_s": offsets[a.slot_id],
                    }
                    for a in self.strike_assignments
                ],
            },
        }


# ---------------------------------------------------------------------------
# UI interface the nodes call back into
# ---------------------------------------------------------------------------


class MenuUI:
    """Interface that menu nodes use to interact with the user.

    The Qt view implements it; tests use a fake.
    """

    def choose_from_list(
        self, node: "MenuNode", options: Sequence[str], current: Optional[str]
    ) -> Optional[str]:
        """Show a dropdown and return the chosen option.

        :param node: The node requesting the choice (used to position the popup).
        :type node: MenuNode
        :param options: Options to offer, in display order.
        :type options: Sequence[str]
        :param current: Currently selected option, shown as checked.
        :type current: str or None
        :returns: The chosen option, or ``None`` if cancelled.
        :rtype: str or None
        :raises NotImplementedError: Always, in this base class.
        """
        raise NotImplementedError

    def ask_number(
        self, title: str, current: float, minimum: float, maximum: float
    ) -> Optional[float]:
        """Ask the operator for a number.

        :param title: Prompt shown to the operator.
        :type title: str
        :param current: Value pre-filled in the input.
        :type current: float
        :param minimum: Smallest accepted value.
        :type minimum: float
        :param maximum: Largest accepted value.
        :type maximum: float
        :returns: The entered value, or ``None`` if cancelled.
        :rtype: float or None
        :raises NotImplementedError: Always, in this base class.
        """
        raise NotImplementedError

    def show_message(self, text: str, modal: bool = False) -> None:
        """Show a message to the operator.

        :param text: Message text.
        :type text: str
        :param modal: If true, show a blocking dialog instead of a status line.
        :type modal: bool
        :raises NotImplementedError: Always, in this base class.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Menu nodes
# ---------------------------------------------------------------------------


class ClickResult(Enum):
    """What the controller should do with a node's child ring after a click."""

    TOGGLE = auto()  #: Open the child ring, or close it if already open.
    OPEN = auto()  #: Make sure the child ring is open.
    CLOSE = auto()  #: Close the child ring (leaf actions, cancelled choices).


class MenuNode:
    """Base class for a button in the radial menu.

    Subclasses override :meth:`children` and :meth:`on_click` to define
    behaviour.

    :param label: Text shown on the button (may contain ``\\n``).
    :type label: str
    :param icon: Short glyph drawn above the label.
    :type icon: str
    """

    def __init__(self, label: str, icon: str = "") -> None:
        """Initialise the node.

        :param label: Text shown on the button.
        :type label: str
        :param icon: Short glyph drawn above the label.
        :type icon: str
        """
        self.label = label
        self.icon = icon

    def children(self, ctx: MissionContext) -> List["MenuNode"]:
        """Return the child buttons shown in the next ring.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Child nodes; empty for a leaf.
        :rtype: list[MenuNode]
        """
        return []

    def on_click(self, ctx: MissionContext, ui: MenuUI) -> ClickResult:
        """Handle a click on this button.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks for dialogs and dropdowns.
        :type ui: MenuUI
        :returns: What to do with this node's child ring.
        :rtype: ClickResult
        """
        return ClickResult.TOGGLE

    def display_label(self, ctx: MissionContext) -> str:
        """Return the label to draw, which may depend on state.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Label text.
        :rtype: str
        """
        return self.label

    def is_selected(self, ctx: MissionContext) -> bool:
        """Return whether the button should be drawn as selected/active.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: ``True`` if the button represents an active choice.
        :rtype: bool
        """
        return False


class GroupNode(MenuNode):
    """A button with a fixed list of children; clicking toggles its ring.

    :param label: Button label.
    :param children: Static child nodes.
    :param icon: Short glyph drawn above the label.
    :param on_open: Optional callback run with the context when clicked.
    :param selected_when: Optional predicate deciding :meth:`is_selected`.
    """

    def __init__(
        self,
        label: str,
        children: Sequence[MenuNode] = (),
        icon: str = "",
        on_open: Optional[Callable[[MissionContext], None]] = None,
        selected_when: Optional[Callable[[MissionContext], bool]] = None,
    ) -> None:
        """Initialise the group.

        :param label: Button label.
        :type label: str
        :param children: Static child nodes.
        :type children: Sequence[MenuNode]
        :param icon: Short glyph drawn above the label.
        :type icon: str
        :param on_open: Callback run with the context when the button is clicked.
        :type on_open: Callable[[MissionContext], None] or None
        :param selected_when: Predicate deciding whether the button is selected.
        :type selected_when: Callable[[MissionContext], bool] or None
        """
        super().__init__(label, icon)
        self._children = list(children)
        self._on_open = on_open
        self._selected_when = selected_when

    def children(self, ctx: MissionContext) -> List[MenuNode]:
        """Return the static children.

        :param ctx: Current mission state (unused).
        :type ctx: MissionContext
        :returns: Child nodes.
        :rtype: list[MenuNode]
        """
        return list(self._children)

    def on_click(self, ctx: MissionContext, ui: MenuUI) -> ClickResult:
        """Run the optional open callback and toggle the child ring.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        :returns: :attr:`ClickResult.TOGGLE`.
        :rtype: ClickResult
        """
        if self._on_open is not None:
            self._on_open(ctx)
        return ClickResult.TOGGLE

    def is_selected(self, ctx: MissionContext) -> bool:
        """Evaluate the optional selection predicate.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Predicate result, or ``False`` if none was given.
        :rtype: bool
        """
        return bool(self._selected_when and self._selected_when(ctx))


class ActionNode(MenuNode):
    """A leaf button that runs a callback.

    :param label: Button label.
    :param action: Callback ``action(ctx, ui)``.
    :param icon: Short glyph drawn above the label.
    """

    def __init__(
        self,
        label: str,
        action: Optional[Callable[[MissionContext, MenuUI], None]] = None,
        icon: str = "",
    ) -> None:
        """Initialise the action.

        :param label: Button label.
        :type label: str
        :param action: Callback run on click with ``(ctx, ui)``.
        :type action: Callable[[MissionContext, MenuUI], None] or None
        :param icon: Short glyph drawn above the label.
        :type icon: str
        """
        super().__init__(label, icon)
        self._action = action

    def run(self, ctx: MissionContext, ui: MenuUI) -> None:
        """Perform the action.  Subclasses may override instead of passing a callback.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        """
        if self._action is not None:
            self._action(ctx, ui)

    def on_click(self, ctx: MissionContext, ui: MenuUI) -> ClickResult:
        """Run the action; leaves have no child ring.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        :returns: :attr:`ClickResult.CLOSE`.
        :rtype: ClickResult
        """
        self.run(ctx, ui)
        return ClickResult.CLOSE


class ExclusiveOptionNode(ActionNode):
    """One option in a mutually exclusive set stored on the context.

    Clicking sets ``ctx.<attr> = value``; clicking the active option clears it.

    :param label: Button label.
    :param attr: Name of the :class:`MissionContext` attribute to set.
    :param value: Value this option represents.
    :param icon: Short glyph drawn above the label.
    """

    def __init__(self, label: str, attr: str, value: str, icon: str = "") -> None:
        """Initialise the option.

        :param label: Button label.
        :type label: str
        :param attr: Context attribute to set.
        :type attr: str
        :param value: Value this option represents.
        :type value: str
        :param icon: Short glyph drawn above the label.
        :type icon: str
        """
        super().__init__(label, icon=icon)
        self.attr = attr
        self.value = value

    def run(self, ctx: MissionContext, ui: MenuUI) -> None:
        """Select this option, or clear it if it is already selected.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        """
        new_value = None if self.is_selected(ctx) else self.value
        setattr(ctx, self.attr, new_value)
        ui.show_message(f"{self.attr} = {new_value}")

    def is_selected(self, ctx: MissionContext) -> bool:
        """Return whether this option is the active one.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: ``True`` if ``ctx.<attr> == value``.
        :rtype: bool
        """
        return getattr(ctx, self.attr) == self.value


class SelectFromListNode(MenuNode):
    """A button that opens a dropdown when clicked.

    Subclasses implement :meth:`options`, :meth:`current` and
    :meth:`apply_choice`.  Once a value is chosen, the child ring opens.
    """

    def options(self, ctx: MissionContext) -> List[str]:
        """Return the options to offer.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Options in display order.
        :rtype: list[str]
        :raises NotImplementedError: In this base class.
        """
        raise NotImplementedError

    def current(self, ctx: MissionContext) -> Optional[str]:
        """Return the currently chosen option.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: The current choice, or ``None``.
        :rtype: str or None
        """
        return None

    def apply_choice(self, ctx: MissionContext, choice: str) -> None:
        """Store the chosen option in the context.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param choice: The option the user picked.
        :type choice: str
        :raises NotImplementedError: In this base class.
        """
        raise NotImplementedError

    def on_click(self, ctx: MissionContext, ui: MenuUI) -> ClickResult:
        """Show the dropdown, apply the choice and open the child ring.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        :returns: :attr:`ClickResult.OPEN` if there is a value and children,
            otherwise :attr:`ClickResult.CLOSE`.
        :rtype: ClickResult
        """
        choice = ui.choose_from_list(self, self.options(ctx), self.current(ctx))
        if choice is not None:
            self.apply_choice(ctx, choice)
        return ClickResult.OPEN if self.children(ctx) else ClickResult.CLOSE


class AssignIsrDroneNode(SelectFromListNode):
    """Button that assigns an ISR drone to the target's ISR lock via a dropdown.

    The dropdown lists ISR drones not tasked on other targets, plus an entry
    that cancels the lock.
    """

    CANCEL = "✕ Cancel ISR lock"

    def __init__(self) -> None:
        """Initialise the button."""
        super().__init__("Assign\nISR drone", icon="◉")

    def options(self, ctx: MissionContext) -> List[str]:
        """Offer free ISR drones plus a cancel-lock entry.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: ISR drone identifiers followed by :attr:`CANCEL`.
        :rtype: list[str]
        """
        return ctx.free_isr_drones() + [self.CANCEL]

    def current(self, ctx: MissionContext) -> Optional[str]:
        """Return the ISR drone tasked with the lock.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: The assigned ISR drone, or ``None``.
        :rtype: str or None
        """
        return ctx.isr_drone

    def apply_choice(self, ctx: MissionContext, choice: str) -> None:
        """Assign the chosen ISR drone, or cancel the lock.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param choice: Chosen drone, or :attr:`CANCEL`.
        :type choice: str
        """
        if choice == self.CANCEL:
            ctx.cancel_isr_lock()
        else:
            ctx.isr_drone = choice

    def display_label(self, ctx: MissionContext) -> str:
        """Show the assigned drone, or the assign prompt.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Label text.
        :rtype: str
        """
        return ctx.isr_drone or self.label

    def is_selected(self, ctx: MissionContext) -> bool:
        """Drawn as selected once a drone is assigned.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: ``True`` if an ISR drone is assigned.
        :rtype: bool
        """
        return ctx.isr_drone is not None


class IsrModeNode(ExclusiveOptionNode):
    """An ISR lock behaviour; once selected, its ring offers drone assignment.

    Unlike :class:`ExclusiveOptionNode`, clicking the active mode does not clear
    it; it only shows or hides the assign-drone ring.  The lock is cancelled
    from the assign-drone dropdown.  Switching modes keeps the assigned drone.

    :param label: Button label.
    :param value: ISR mode identifier stored in ``ctx.isr_mode``.
    :param assign_node: Shared assign-drone button shown as the only child.
    :param icon: Short glyph drawn above the label.
    """

    def __init__(self, label: str, value: str, assign_node: MenuNode, icon: str = "") -> None:
        """Initialise the mode button.

        :param label: Button label.
        :type label: str
        :param value: ISR mode identifier.
        :type value: str
        :param assign_node: Shared assign-drone button.
        :type assign_node: MenuNode
        :param icon: Short glyph drawn above the label.
        :type icon: str
        """
        super().__init__(label, "isr_mode", value, icon=icon)
        self._assign_node = assign_node

    def run(self, ctx: MissionContext, ui: MenuUI) -> None:
        """Select this mode.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        """
        ctx.isr_mode = self.value
        ui.show_message(f"isr_mode = {self.value}")

    def on_click(self, ctx: MissionContext, ui: MenuUI) -> ClickResult:
        """Select the mode and open its ring; toggle the ring if already active.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        :returns: :attr:`ClickResult.TOGGLE` if the mode was already active,
            otherwise :attr:`ClickResult.OPEN`.
        :rtype: ClickResult
        """
        was_selected = self.is_selected(ctx)
        self.run(ctx, ui)
        return ClickResult.TOGGLE if was_selected else ClickResult.OPEN

    def children(self, ctx: MissionContext) -> List[MenuNode]:
        """Show the assign-drone button while this mode is active.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: ``[assign_node]`` if selected, else ``[]``.
        :rtype: list[MenuNode]
        """
        return [self._assign_node] if self.is_selected(ctx) else []


class StrikeVectorNode(ActionNode):
    """Placeholder button for setting a strike vector on a drone slot.

    :param slot_id: Slot whose vector this button sets.
    """

    def __init__(self, slot_id: int) -> None:
        """Initialise the button.

        :param slot_id: Slot whose vector this button sets.
        :type slot_id: int
        """
        super().__init__("Strike\nvector\n(optional)", icon="➹")
        self.slot_id = slot_id

    def run(self, ctx: MissionContext, ui: MenuUI) -> None:
        """Tell the operator that vector setting is not implemented yet.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        """
        slot = ctx.slot(self.slot_id)
        drone = slot.drone_id if slot else "?"
        ui.show_message(f"Strike vector for {drone}: not implemented yet")


def _fmt_seconds(seconds: float) -> str:
    """Format a duration without a trailing ``.0``.

    :param seconds: Duration in seconds.
    :type seconds: float
    :returns: e.g. ``"10 s"`` or ``"2.5 s"``.
    :rtype: str
    """
    return f"{seconds:g} s"


class StrikeTimingNode(ActionNode):
    """Button that sets how long after the previous strike this slot strikes.

    The first slot always strikes at T+0, so its button only explains that.

    :param slot_id: Slot whose delay this button sets.
    """

    def __init__(self, slot_id: int) -> None:
        """Initialise the button.

        :param slot_id: Slot whose delay this button sets.
        :type slot_id: int
        """
        super().__init__("Strike\ntiming", icon="⏱")
        self.slot_id = slot_id

    def display_label(self, ctx: MissionContext) -> str:
        """Show the first strike as T+0 and later ones as their delay.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Label text.
        :rtype: str
        """
        slot = ctx.slot(self.slot_id)
        if slot is None or ctx.is_first_slot(self.slot_id):
            return "Strike at\nT+0 (first)"
        return f"+{_fmt_seconds(slot.delay_s)}\nafter prev."

    def run(self, ctx: MissionContext, ui: MenuUI) -> None:
        """Ask for the delay and store it on the slot.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        """
        slot = ctx.slot(self.slot_id)
        if slot is None:
            return
        if ctx.is_first_slot(self.slot_id):
            ui.show_message("First strike at T+0; set the delay on the later slots")
            return
        value = ui.ask_number(
            "Seconds after the previous strike (0 = simultaneous)",
            slot.delay_s,
            0.0,
            MAX_STRIKE_DELAY_S,
        )
        if value is not None:
            slot.delay_s = value
            ui.show_message(f"{slot.drone_id}: strikes {_fmt_seconds(value)} after the previous drone")


class DroneSlotNode(SelectFromListNode):
    """A strike-drone slot; clicking opens a dropdown of free strike drones.

    :param slot_id: Identifier of the :class:`DroneAssignment` it edits.
    """

    REMOVE = "✕ Remove this slot"

    def __init__(self, slot_id: int) -> None:
        """Initialise the slot button.

        :param slot_id: Identifier of the slot this button edits.
        :type slot_id: int
        """
        super().__init__(f"Slot {slot_id}", icon="✈")
        self.slot_id = slot_id
        self._timing_node = StrikeTimingNode(slot_id)
        self._vector_node = StrikeVectorNode(slot_id)

    def options(self, ctx: MissionContext) -> List[str]:
        """Offer free drones plus a remove-slot entry.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Drone identifiers followed by :attr:`REMOVE`.
        :rtype: list[str]
        """
        return ctx.free_drones(for_slot_id=self.slot_id) + [self.REMOVE]

    def current(self, ctx: MissionContext) -> Optional[str]:
        """Return the drone in this slot.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: The assigned drone, or ``None``.
        :rtype: str or None
        """
        slot = ctx.slot(self.slot_id)
        return slot.drone_id if slot else None

    def apply_choice(self, ctx: MissionContext, choice: str) -> None:
        """Assign the chosen drone, or remove the slot.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param choice: Chosen drone, or :attr:`REMOVE`.
        :type choice: str
        """
        if choice == self.REMOVE:
            ctx.remove_slot(self.slot_id)
            return
        slot = ctx.slot(self.slot_id)
        if slot is not None:
            slot.drone_id = choice

    def children(self, ctx: MissionContext) -> List[MenuNode]:
        """Show the timing and strike-vector buttons once a drone is chosen.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: ``[StrikeTimingNode, StrikeVectorNode]`` if a drone is assigned, else ``[]``.
        :rtype: list[MenuNode]
        """
        return [self._timing_node, self._vector_node] if self.current(ctx) else []

    def display_label(self, ctx: MissionContext) -> str:
        """Show the drone name, or a prompt if none is chosen.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Label text.
        :rtype: str
        """
        return self.current(ctx) or "Select\ndrone…"

    def is_selected(self, ctx: MissionContext) -> bool:
        """A slot is drawn as selected once it has a drone.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: ``True`` if a drone is assigned.
        :rtype: bool
        """
        return self.current(ctx) is not None


class DynamicListNode(MenuNode):
    """A button whose every click adds one more item to its child ring.

    Child nodes are cached by key so they stay the same objects across clicks,
    which keeps the controller's open path valid.

    :param label: Button label.
    :param add_item: Callback that adds an item to the context and returns its key.
    :param item_keys: Callback returning the keys of the current items, in order.
    :param make_node: Factory creating the child node for a key.
    :param icon: Short glyph drawn above the label.
    """

    def __init__(
        self,
        label: str,
        add_item: Callable[[MissionContext], int],
        item_keys: Callable[[MissionContext], List[int]],
        make_node: Callable[[int], MenuNode],
        icon: str = "",
    ) -> None:
        """Initialise the list button.

        :param label: Button label.
        :type label: str
        :param add_item: Adds an item to the context and returns its key.
        :type add_item: Callable[[MissionContext], int]
        :param item_keys: Returns the keys of the current items, in order.
        :type item_keys: Callable[[MissionContext], list[int]]
        :param make_node: Creates the child node for a key.
        :type make_node: Callable[[int], MenuNode]
        :param icon: Short glyph drawn above the label.
        :type icon: str
        """
        super().__init__(label, icon)
        self._add_item = add_item
        self._item_keys = item_keys
        self._make_node = make_node
        self._cache: Dict[int, MenuNode] = {}

    def children(self, ctx: MissionContext) -> List[MenuNode]:
        """Return one cached child node per current item.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :returns: Child nodes in item order.
        :rtype: list[MenuNode]
        """
        nodes = []
        for key in self._item_keys(ctx):
            if key not in self._cache:
                self._cache[key] = self._make_node(key)
            nodes.append(self._cache[key])
        return nodes

    def on_click(self, ctx: MissionContext, ui: MenuUI) -> ClickResult:
        """Add one item and keep the child ring open.

        :param ctx: Current mission state.
        :type ctx: MissionContext
        :param ui: UI callbacks.
        :type ui: MenuUI
        :returns: :attr:`ClickResult.OPEN`.
        :rtype: ClickResult
        """
        self._add_item(ctx)
        ui.show_message(f"{self.label.replace(chr(10), ' ')}: {len(self._item_keys(ctx))} item(s)")
        return ClickResult.OPEN


# ---------------------------------------------------------------------------
# Menu definition
# ---------------------------------------------------------------------------


def _show_geolocation(ctx: MissionContext, ui: MenuUI) -> None:
    """Show the target's geolocation (stub for the global-map view).

    :param ctx: Current mission state.
    :type ctx: MissionContext
    :param ui: UI callbacks.
    :type ui: MenuUI
    """
    t = ctx.target
    ui.show_message(
        f"{t.target_id} ({t.label})\nlat {t.lat:.5f}, lon {t.lon:.5f}\n\n"
        "(Global map view not implemented yet.)",
        modal=True,
    )


def _set_strike_target(ctx: MissionContext) -> None:
    """Mark the target as a strike target.

    :param ctx: Current mission state.
    :type ctx: MissionContext
    """
    ctx.is_strike_target = True


def build_target_menu(target: Target) -> MenuNode:
    """Build the radial menu tree for an ATR target.

    :param target: The target the menu acts on.
    :type target: Target
    :returns: Root node, drawn as the centre circle.
    :rtype: MenuNode
    """
    assign_isr = AssignIsrDroneNode()
    isr_modes = [
        IsrModeNode("Hover\nand hold", "hover_hold", assign_isr, icon="⏸"),
        IsrModeNode("Maintain\ndist/heading", "maintain_distance_heading", assign_isr, icon="⇢"),
        IsrModeNode("Orbit\ntarget", "orbit", assign_isr, icon="⟳"),
    ]
    add_drone = DynamicListNode(
        "Add strike\ndrone",
        add_item=lambda ctx: ctx.add_slot().slot_id,
        item_keys=lambda ctx: [a.slot_id for a in ctx.strike_assignments],
        make_node=DroneSlotNode,
        icon="＋",
    )
    return GroupNode(
        target.target_id,
        children=[
            ActionNode("Show\ngeolocation", _show_geolocation, icon="⌖"),
            GroupNode(
                "Lock ISR\non target",
                isr_modes,
                icon="◎",
                selected_when=lambda ctx: ctx.isr_mode is not None,
            ),
            GroupNode(
                "Set as strike\ntarget",
                [add_drone],
                icon="✸",
                on_open=_set_strike_target,
                selected_when=lambda ctx: ctx.is_strike_target,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Open-ring state
# ---------------------------------------------------------------------------


@dataclass
class Ring:
    """One visible ring of buttons.

    :param level: Ring number, 1 for the innermost ring.
    :param parent: Node whose children this ring shows.
    :param nodes: The buttons in the ring, in clockwise order.
    """

    level: int
    parent: MenuNode
    nodes: List[MenuNode]


class MenuController:
    """Track which rings of a radial menu are open and dispatch clicks.

    ``open_path[0]`` is the root (the selected target).  ``open_path[k]`` is the node
    opened from ring ``k``.  Each open node shows its children in the next ring.
    The view opens the root when a target is selected; an empty path shows no rings.

    :param root: Root node of the menu.
    :param ctx: Mission state the menu acts on.
    """

    def __init__(self, root: MenuNode, ctx: MissionContext) -> None:
        """Initialise with all rings closed.

        :param root: Root node of the menu.
        :type root: MenuNode
        :param ctx: Mission state the menu acts on.
        :type ctx: MissionContext
        """
        self.root = root
        self.ctx = ctx
        self.open_path: List[MenuNode] = []

    def _prune(self) -> None:
        """Close open nodes that are gone or have nothing left to show.

        This happens when, for example, a drone slot is removed or the ISR
        lock is cancelled.
        """
        if not self.open_path:
            return
        valid = [self.open_path[0]]
        for node in self.open_path[1:]:
            if node in valid[-1].children(self.ctx) and node.children(self.ctx):
                valid.append(node)
            else:
                break
        self.open_path = valid

    def rings(self) -> List[Ring]:
        """Return the rings that should be visible, innermost first.

        :returns: One :class:`Ring` per open node.
        :rtype: list[Ring]
        """
        self._prune()
        return [
            Ring(level=i + 1, parent=node, nodes=node.children(self.ctx))
            for i, node in enumerate(self.open_path)
        ]

    def is_open(self, node: MenuNode) -> bool:
        """Return whether a node's child ring is open.

        :param node: Node to check.
        :type node: MenuNode
        :returns: ``True`` if the node is on the open path.
        :rtype: bool
        """
        return node in self.open_path

    def click(self, node: MenuNode, level: int, ui: MenuUI) -> ClickResult:
        """Handle a click on a button.

        :param node: The clicked node.
        :type node: MenuNode
        :param level: Ring the node is in (1 for the innermost ring; 0 for the root).
        :type level: int
        :param ui: UI callbacks passed to the node.
        :type ui: MenuUI
        :returns: The node's click result.
        :rtype: ClickResult
        """
        was_open = len(self.open_path) > level and self.open_path[level] is node
        result = node.on_click(self.ctx, ui)
        del self.open_path[level:]
        if result is ClickResult.OPEN or (result is ClickResult.TOGGLE and not was_open):
            if node.children(self.ctx):
                self.open_path.append(node)
        self._prune()
        return result


# ---------------------------------------------------------------------------
# Ring geometry (pure functions)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RingStyle:
    """Sizes used to lay out the rings.

    :param center_radius: Radius of the centre circle in pixels.
    :param ring_width: Radial thickness of each ring in pixels.
    :param ring_gap: Radial gap between rings in pixels.
    :param max_arc: Largest arc length a single button may take, measured at the
        ring's mid radius.  With few options the ring is only partly filled.
    :param gap_px: Gap between neighbouring buttons, measured at mid radius.
    """

    center_radius: float = 42.0
    ring_width: float = 74.0
    ring_gap: float = 6.0
    max_arc: float = 112.0
    gap_px: float = 5.0


def ring_radii(level: int, style: RingStyle) -> Tuple[float, float]:
    """Return the inner and outer radius of a ring.

    :param level: Ring number, 1 for the innermost ring.
    :type level: int
    :param style: Layout sizes.
    :type style: RingStyle
    :returns: ``(inner_radius, outer_radius)`` in pixels.
    :rtype: tuple[float, float]
    """
    r_in = style.center_radius + style.ring_gap + (level - 1) * (style.ring_width + style.ring_gap)
    return r_in, r_in + style.ring_width


def fan_layout(
    n: int, center_deg: float, max_sweep_deg: float, gap_deg: float = 0.0
) -> List[Tuple[float, float]]:
    """Lay out ``n`` equal buttons in a fan centred on an angle.

    Each button gets ``min(360 / n, max_sweep_deg)`` degrees, so a few options
    fill only part of the ring and many options split the full circle evenly.
    Angles are in degrees, counter-clockwise from 3 o'clock (Qt convention).
    Buttons are returned in clockwise order, so index 0 is the left-most
    button of a fan at the top.

    :param n: Number of buttons.
    :type n: int
    :param center_deg: Angle the fan is centred on.
    :type center_deg: float
    :param max_sweep_deg: Largest angle a single button may take.
    :type max_sweep_deg: float
    :param gap_deg: Angle left empty between neighbouring buttons.
    :type gap_deg: float
    :returns: ``(start_deg, sweep_deg)`` per button, with positive sweep.
    :rtype: list[tuple[float, float]]
    """
    if n <= 0:
        return []
    slot = min(360.0 / n, max_sweep_deg)
    left_edge = center_deg + slot * n / 2.0
    layout = []
    for i in range(n):
        end = left_edge - i * slot
        start = end - slot
        layout.append((start + gap_deg / 2.0, slot - gap_deg))
    return layout


def ring_fan(n: int, level: int, center_deg: float, style: RingStyle) -> List[Tuple[float, float]]:
    """Lay out ``n`` buttons in a ring so that each button has a similar size.

    The size limits in ``style`` are arc lengths in pixels, so outer rings use
    smaller angles per button.

    :param n: Number of buttons.
    :type n: int
    :param level: Ring number, 1 for the innermost ring.
    :type level: int
    :param center_deg: Angle the fan is centred on.
    :type center_deg: float
    :param style: Layout sizes.
    :type style: RingStyle
    :returns: ``(start_deg, sweep_deg)`` per button.
    :rtype: list[tuple[float, float]]
    """
    r_in, r_out = ring_radii(level, style)
    r_mid = (r_in + r_out) / 2.0
    max_sweep = math.degrees(style.max_arc / r_mid)
    gap = math.degrees(style.gap_px / r_mid)
    return fan_layout(n, center_deg, max_sweep, gap)


def polar_to_xy(cx: float, cy: float, radius: float, angle_deg: float) -> Tuple[float, float]:
    """Convert a polar position to screen coordinates (y axis pointing down).

    :param cx: Centre x.
    :type cx: float
    :param cy: Centre y.
    :type cy: float
    :param radius: Distance from the centre.
    :type radius: float
    :param angle_deg: Angle counter-clockwise from 3 o'clock.
    :type angle_deg: float
    :returns: ``(x, y)`` screen position.
    :rtype: tuple[float, float]
    """
    a = math.radians(angle_deg)
    return cx + radius * math.cos(a), cy - radius * math.sin(a)
