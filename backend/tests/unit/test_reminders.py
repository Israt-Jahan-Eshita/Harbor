"""Unit tests for meal-timed reminders and idempotent tick state machine (core/reminders.py)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.reminders import build_dose_schedule, evaluate_tick, mark_dose_taken
from app.core.types import MedicineData

DHAKA = ZoneInfo("Asia/Dhaka")


def test_schedule_offsets_and_unconfirmed_guard() -> None:
    meal_times = {"breakfast": "08:00", "lunch": "13:30", "dinner": "21:00"}
    unconfirmed = MedicineData(
        id="med-u", name_as_written="Enalapril", timing="after_food",
        meal_slots=["dinner"], verified_by_caregiver=False, active=True,
    )
    assert build_dose_schedule(unconfirmed, "m1", "মা", meal_times, date(2026, 11, 25)) == []

    confirmed_after = MedicineData(
        id="med-1", name_as_written="Enalapril", drug_class="ace_inhibitor",
        timing="after_food", meal_slots=["dinner"], verified_by_caregiver=True, active=True,
    )
    doses = build_dose_schedule(confirmed_after, "m1", "মা", meal_times, date(2026, 11, 25))
    assert len(doses) == 1
    assert doses[0].due_at == datetime(2026, 11, 25, 21, 20, tzinfo=DHAKA)
    assert doses[0].window_end == datetime(2026, 11, 25, 21, 50, tzinfo=DHAKA)

    confirmed_before = MedicineData(
        id="med-2", name_as_written="Med2", drug_class="none_modelled",
        timing="before_food", meal_slots=["breakfast"], verified_by_caregiver=True, active=True,
    )
    doses_b = build_dose_schedule(confirmed_before, "m1", "মা", meal_times, date(2026, 11, 25))
    assert doses_b[0].due_at == datetime(2026, 11, 25, 7, 30, tzinfo=DHAKA)


def test_tick_due_escalation_idempotency_and_generic_text() -> None:
    meal_times = {"dinner": "21:00"}
    med = MedicineData(
        id="med-1", name_as_written="Enalapril", drug_class="ace_inhibitor",
        timing="after_food", meal_slots=["dinner"], verified_by_caregiver=True, active=True,
    )
    doses = build_dose_schedule(med, "m1", "মা", meal_times, date(2026, 11, 25))

    # 1. Tick at due time (21:20) -> generic notification, no disease or medicine name
    t_due = datetime(2026, 11, 25, 21, 20, tzinfo=DHAKA)
    tick1 = evaluate_tick(doses, now=t_due)
    assert len(tick1["patient_notifications"]) == 1
    notif_text = tick1["patient_notifications"][0]["text"]
    assert notif_text == "ওষুধের সময় হয়েছে"
    assert "Enalapril" not in notif_text
    assert "diabetes" not in notif_text.lower()
    assert "hypertension" not in notif_text.lower()
    assert tick1["doses"][0].status == "pending"

    # 2. Idempotent repeated tick at 21:25 -> no duplicate notification
    tick2 = evaluate_tick(tick1["doses"], now=t_due + timedelta(minutes=5), existing_alert_keys=tick1["alert_keys"])
    assert tick2["patient_notifications"] == []
    assert tick2["caregiver_escalations"] == []

    # 3. Tick past grace window (21:51) -> missed -> escalated + caregiver alert
    t_late = datetime(2026, 11, 25, 21, 51, tzinfo=DHAKA)
    tick3 = evaluate_tick(tick2["doses"], now=t_late, existing_alert_keys=tick2["alert_keys"])
    assert tick3["doses"][0].status == "escalated"
    assert len(tick3["caregiver_escalations"]) == 1

    # 4. Repeated tick after escalation -> idempotent, no duplicate escalation
    tick4 = evaluate_tick(tick3["doses"], now=t_late + timedelta(minutes=10), existing_alert_keys=tick3["alert_keys"])
    assert tick4["caregiver_escalations"] == []

    # 5. Late confirmation transitions escalated -> taken_late and is idempotent
    taken_late = mark_dose_taken(tick4["doses"][0], now=t_late + timedelta(minutes=15))
    assert taken_late.status == "taken_late"
    assert mark_dose_taken(taken_late, now=t_late + timedelta(minutes=20)).confirmed_at == taken_late.confirmed_at


def test_pending_to_taken_happy_path() -> None:
    med = MedicineData(
        id="med-1", name_as_written="Enalapril", drug_class="ace_inhibitor",
        timing="with_food", meal_slots=["dinner"], verified_by_caregiver=True, active=True,
    )
    doses = build_dose_schedule(med, "m1", "মা", {"dinner": "21:00"}, date(2026, 11, 25))
    taken = mark_dose_taken(doses[0], now=datetime(2026, 11, 25, 21, 5, tzinfo=DHAKA))
    assert taken.status == "taken"
    res = evaluate_tick([taken], now=datetime(2026, 11, 25, 22, 0, tzinfo=DHAKA))
    assert res["patient_notifications"] == []
    assert res["caregiver_escalations"] == []
