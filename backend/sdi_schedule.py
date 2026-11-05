from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

TZ = ZoneInfo("Europe/Rome")
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class ScheduleIn(BaseModel):
    enabled: bool = False
    modo: Literal["intervallo", "orari"] = "intervallo"
    ogni_minuti: int = Field(default=60, ge=5, le=1440)
    dalle: str = Field(default="07:00", pattern=_HHMM)
    alle: str = Field(default="20:00", pattern=_HHMM)
    orari: List[str] = Field(default_factory=lambda: ["08:00", "13:00", "18:00"], max_length=24)
    giorni: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)
    passive: bool = True
    notifiche: bool = True

    @field_validator("orari")
    @classmethod
    def _o(cls, v):
        import re
        v = sorted({x.strip() for x in v if x.strip()})
        for x in v:
            if not re.fullmatch(_HHMM, x):
                raise ValueError(f"Orario non valido: {x} (usa il formato HH:MM)")
        return v

    @field_validator("giorni")
    @classmethod
    def _g(cls, v):
        v = sorted(set(v))
        if not v or any(d < 0 or d > 6 for d in v):
            raise ValueError("Scegli almeno un giorno della settimana")
        return v

    @model_validator(mode="after")
    def _c(self):
        if self.modo == "orari" and not self.orari:
            raise ValueError("Inserisci almeno un orario")
        if self.modo == "intervallo" and self.dalle >= self.alle:
            raise ValueError("L'orario di inizio deve precedere quello di fine")
        if not (self.passive or self.notifiche):
            raise ValueError("Scegli almeno cosa ricevere: fatture passive o notifiche")
        return self


def _at(day: datetime, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def next_run(s: dict, after: Optional[datetime] = None) -> Optional[str]:
    if not s.get("enabled"):
        return None
    now = (after or datetime.now(timezone.utc)).astimezone(TZ)
    for d in range(8):
        day = now + timedelta(days=d)
        if day.weekday() not in s["giorni"]:
            continue
        if s["modo"] == "orari":
            slots = [_at(day, x) for x in s["orari"]]
        else:
            start, end, step = _at(day, s["dalle"]), _at(day, s["alle"]), timedelta(minutes=s["ogni_minuti"])
            slots = []
            t = start
            while t <= end:
                slots.append(t)
                t += step
        for t in slots:
            if t > now:
                return t.astimezone(timezone.utc).isoformat()
    return None


def describe(s: dict) -> str:
    if not s.get("enabled"):
        return "Ricezione automatica disattivata"
    g = ", ".join(GIORNI[d] for d in s["giorni"])
    if s["modo"] == "orari":
        return f"Alle {', '.join(s['orari'])} · {g}"
    ogni = f"{s['ogni_minuti'] // 60} ore" if s["ogni_minuti"] % 60 == 0 and s["ogni_minuti"] >= 120 else ("1 ora" if s["ogni_minuti"] == 60 else f"{s['ogni_minuti']} minuti")
    return f"Ogni {ogni} dalle {s['dalle']} alle {s['alle']} · {g}"
