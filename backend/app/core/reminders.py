"""Meal-timed medicine reminder scheduler and idempotent escalation state machine — pure Python."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.types import DoseRecord, MedicineData

DEFAULT_OFFSETS_MIN: dict[str, int] = {
    "after_food": 20,
    "before_food": -30,
    "with_food": 0,
    "any": 0,
    "unknown": 0,
}

GENERIC_REMINDER_TEXT_BN = "ওষুধের সময় হয়েছে"


def build_dose_schedule(
    medicine: MedicineData,
    member_id: str,
    member_name: str,
    meal_times: dict[str, str],
    for_date: date,
    offsets_min: dict[str, int] | None = None,
    grace_minutes: int = 30,
    tz_name: str = "Asia/Dhaka",
) -> list[DoseRecord]:
    """Generate timezone-aware dose schedule rows only for confirmed active medicines."""
    if not medicine.verified_by_caregiver or not medicine.active:
        return []

    offsets = {**DEFAULT_OFFSETS_MIN, **(offsets_min or {})}
    offset = offsets.get(medicine.timing, 0)
    tz = ZoneInfo(tz_name)

    slots = medicine.meal_slots if medicine.meal_slots else ["dinner"]
    records: list[DoseRecord] = []

    for idx, slot in enumerate(slots):
        hhmm = meal_times.get(slot)
        if not hhmm:
            continue
        hour_str, min_str = hhmm.split(":")
        meal_dt = datetime.combine(for_date, time(int(hour_str), int(min_str)), tzinfo=tz)
        due_at = meal_dt + timedelta(minutes=offset)
        window_end = due_at + timedelta(minutes=grace_minutes)

        records.append(
            DoseRecord(
                id=f"{medicine.id or medicine.name_as_written}:{for_date.isoformat()}:{slot}:{idx}",
                medicine_id=medicine.id,
                member_id=member_id,
                member_name=member_name,
                due_at=due_at,
                window_end=window_end,
                status="pending",
            )
        )

    return records


def evaluate_tick(
    doses: list[DoseRecord],
    now: datetime,
    existing_alert_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Run idempotent tick evaluation across dose records.

    - Never includes disease or medicine names in patient/lock-screen notifications.
    - Pending doses whose due_at <= now <= window_end emit a generic due alert once.
    - Pending doses past window_end transition pending -> missed -> escalated once.
    """
    sent_keys = set(existing_alert_keys or set())
    patient_notifications: list[dict[str, Any]] = []
    caregiver_escalations: list[dict[str, Any]] = []
    updated_doses: list[DoseRecord] = []

    for dose in doses:
        updated = dose.model_copy(deep=True)
        if updated.status == "pending":
            if updated.due_at <= now <= updated.window_end:
                key = f"dose_due:{updated.id}"
                if key not in sent_keys:
                    sent_keys.add(key)
                    patient_notifications.append(
                        {
                            "alert_key": key,
                            "kind": "dose_due",
                            "dose_id": updated.id,
                            "member_id": updated.member_id,
                            "text": GENERIC_REMINDER_TEXT_BN,
                        }
                    )
            elif now > updated.window_end:
                # pending -> missed -> escalated
                updated.status = "escalated"
                esc_key = f"dose_escalated:{updated.id}"
                if esc_key not in sent_keys:
                    sent_keys.add(esc_key)
                    caregiver_escalations.append(
                        {
                            "alert_key": esc_key,
                            "kind": "dose_missed_escalated",
                            "dose_id": updated.id,
                            "member_id": updated.member_id,
                            "member_name": updated.member_name,
                            "text": f"{updated.member_name}-এর একটি ডোজ এখনও নিশ্চিত হয়নি।",
                        }
                    )
        elif updated.status == "missed":
            updated.status = "escalated"
            esc_key = f"dose_escalated:{updated.id}"
            if esc_key not in sent_keys:
                sent_keys.add(esc_key)
                caregiver_escalations.append(
                    {
                        "alert_key": esc_key,
                        "kind": "dose_missed_escalated",
                        "dose_id": updated.id,
                        "member_id": updated.member_id,
                        "member_name": updated.member_name,
                        "text": f"{updated.member_name}-এর একটি ডোজ এখনও নিশ্চিত হয়নি।",
                    }
                )

        updated_doses.append(updated)

    return {
        "doses": updated_doses,
        "patient_notifications": patient_notifications,
        "caregiver_escalations": caregiver_escalations,
        "alert_keys": sent_keys,
    }


def mark_dose_taken(dose: DoseRecord, now: datetime) -> DoseRecord:
    """Idempotently confirm a dose as taken (or taken_late if already missed/escalated)."""
    updated = dose.model_copy(deep=True)
    if updated.status in ("taken", "taken_late"):
        return updated
    if updated.status == "pending":
        updated.status = "taken"
        updated.confirmed_at = now
    else:
        updated.status = "taken_late"
        updated.confirmed_at = now
    return updated
