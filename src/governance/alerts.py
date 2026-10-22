"""Alert levels implementing AVF P3 Monotonic Restriction."""

import enum


class AlertLevel(enum.IntEnum):
    """
    Fire alert levels implementing P3 (Monotonic Restriction).
    Transitions are one-way: MONITOR → WATCH → WARNING → EMERGENCY.
    Downgrading requires explicit human override.
    """
    MONITOR = 0    # Normal — fire is being tracked
    WATCH = 1      # Elevated — indicators suggest increasing risk
    WARNING = 2    # High risk — fire is dangerous and growing
    EMERGENCY = 3  # Critical — immediate response required

    @classmethod
    def from_string(cls, s: str) -> "AlertLevel":
        return cls[s.upper()] if s.upper() in cls.__members__ else cls.MONITOR

    def badge_color(self) -> str:
        return {
            AlertLevel.MONITOR: "#3b82f6",    # Blue
            AlertLevel.WATCH: "#f5a623",       # Yellow
            AlertLevel.WARNING: "#ff8c00",     # Orange
            AlertLevel.EMERGENCY: "#ff3b3b",   # Red
        }[self]
