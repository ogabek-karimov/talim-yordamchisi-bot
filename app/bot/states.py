"""FSM state groups."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ApplyForm(StatesGroup):
    name = State()
    phone = State()
    confirm = State()


class RejectForm(StatesGroup):
    reason = State()
