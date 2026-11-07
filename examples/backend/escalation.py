"""Escalation engine: notify contacts, call them in order until someone acknowledges.

NOTE: this backend only reaches *contacts*. The call to emergency services (112)
is placed by the phone itself, because carriers/Twilio do not let a server place
emergency calls on a user's behalf.
"""
import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol

E164 = re.compile(r"^\+[1-9]\d{7,14}$")

# (delay seconds from incident start, action, target) ; target: "all" | contact index
DEFAULT_POLICY = [
    (0, "sms", "all"),
    (45, "call", 0),
    (105, "call", 1),
    (165, "call", 2),
    (240, "sms", "all"),
]


@dataclass
class Contact:
    name: str
    phone: str


@dataclass
class Incident:
    id: str
    user_name: str
    lat: float
    lon: float
    accuracy: float
    probability: float
    contacts: list
    medical: dict = field(default_factory=dict)
    status: str = "active"           # active | cancelled | acknowledged | completed
    acked_by: Optional[str] = None
    created: float = field(default_factory=time.time)
    events: list = field(default_factory=list)
    track: list = field(default_factory=list)


class Notifier(Protocol):
    async def sms(self, to: str, body: str) -> None: ...
    async def call(self, to: str, say: str) -> None: ...


class ConsoleNotifier:
    async def sms(self, to, body):
        print(f"[SMS -> {to}] {body}")

    async def call(self, to, say):
        print(f"[CALL -> {to}] {say}")


class TwilioNotifier:
    """Minimal Twilio REST client (no SDK). Env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM."""

    def __init__(self, sid, token, from_number):
        import httpx
        self.sid, self.from_ = sid, from_number
        self.http = httpx.AsyncClient(auth=(sid, token), timeout=15)
        self.base = f"https://api.twilio.com/2010-04-01/Accounts/{sid}"

    async def sms(self, to, body):
        r = await self.http.post(f"{self.base}/Messages.json",
                                 data={"To": to, "From": self.from_, "Body": body})
        r.raise_for_status()

    async def call(self, to, say):
        twiml = f"<Response><Say loop='3'>{say}</Say></Response>"
        r = await self.http.post(f"{self.base}/Calls.json",
                                 data={"To": to, "From": self.from_, "Twiml": twiml})
        r.raise_for_status()


def sms_text(i: Incident, base_url: str) -> str:
    med = i.medical or {}
    extra = f" Blood group: {med['blood_group']}." if med.get("blood_group") else ""
    return (f"EMERGENCY: {i.user_name} may have been in a crash.{extra} "
            f"Live location: {base_url}/t/{i.id} "
            f"(https://maps.google.com/?q={i.lat},{i.lon}). Please call them or 112 now.")


class Escalator:
    def __init__(self, notifier: Notifier, base_url="http://localhost:8000", policy=None):
        self.n, self.base_url = notifier, base_url
        self.policy = policy or DEFAULT_POLICY
        self.incidents: dict[str, Incident] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    def create(self, **kw) -> Incident:
        for c in kw["contacts"]:
            if not E164.match(c.phone):
                raise ValueError(f"phone must be E.164: {c.phone}")
        inc = Incident(id=uuid.uuid4().hex[:12], **kw)
        self.incidents[inc.id] = inc
        self.tasks[inc.id] = asyncio.create_task(self._run(inc))
        return inc

    def _log(self, inc, what):
        inc.events.append({"t": round(time.time() - inc.created, 2), "event": what})

    async def _run(self, inc: Incident):
        start = time.monotonic()
        try:
            for delay, action, target in self.policy:
                wait = delay - (time.monotonic() - start)
                if wait > 0:
                    await asyncio.sleep(wait)
                if inc.status != "active":
                    return
                targets = (inc.contacts if target == "all"
                           else inc.contacts[target:target + 1])
                for c in targets:
                    try:
                        if action == "sms":
                            await self.n.sms(c.phone, sms_text(inc, self.base_url))
                        else:
                            await self.n.call(c.phone, f"Emergency. {inc.user_name} may have been in "
                                              "a crash. Check your text messages for their location.")
                        self._log(inc, f"{action}:{c.name}")
                    except Exception as e:  # keep escalating even if one send fails
                        self._log(inc, f"{action}_failed:{c.name}:{type(e).__name__}")
            if inc.status == "active":
                inc.status = "completed"
        except asyncio.CancelledError:
            pass

    async def cancel(self, iid: str):
        inc = self.incidents[iid]
        if inc.status != "active":
            return inc
        inc.status = "cancelled"
        self._log(inc, "cancelled_by_user")
        notified = {e["event"].split(":", 1)[1] for e in inc.events if e["event"].startswith("sms:")}
        for c in inc.contacts:
            if c.name in notified:
                await self.n.sms(c.phone, f"False alarm: {inc.user_name} is OK. Sorry for the scare.")
        return inc

    def ack(self, iid: str, phone: str):
        inc = self.incidents[iid]
        if inc.status == "active":
            inc.status, inc.acked_by = "acknowledged", phone
            self._log(inc, f"acknowledged:{phone}")
        return inc

    def update_location(self, iid, lat, lon):
        inc = self.incidents[iid]
        inc.lat, inc.lon = lat, lon
        inc.track.append((round(time.time(), 1), lat, lon))
        return inc
