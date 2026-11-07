import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from app import create_app
from escalation import Contact, Escalator

FAST = [(0, "sms", "all"), (0.15, "call", 0), (0.3, "call", 1), (0.45, "call", 2)]
CONTACTS = [Contact("Amma", "+919800000001"), Contact("Achan", "+919800000002"),
            Contact("Friend", "+919800000003")]


class Fake:
    def __init__(self):
        self.log = []

    async def sms(self, to, body):
        self.log.append(("sms", to, body))

    async def call(self, to, say):
        self.log.append(("call", to))


def mk(fake):
    return Escalator(fake, "http://t", FAST)


def new(esc):
    return esc.create(user_name="Nistal", lat=9.99, lon=76.3, accuracy=5, probability=0.97,
                      contacts=CONTACTS, medical={"blood_group": "O+"})


def test_sms_all_then_calls_in_order():
    async def go():
        f = Fake(); e = mk(f); inc = new(e)
        await asyncio.sleep(0.7)
        assert [x[:2] for x in f.log if x[0] == "sms"] == [("sms", c.phone) for c in CONTACTS]
        assert [x[1] for x in f.log if x[0] == "call"] == [c.phone for c in CONTACTS]
        assert "O+" in f.log[0][2] and f"/t/{inc.id}" in f.log[0][2]
        assert inc.status == "completed"
    asyncio.run(go())


def test_ack_stops_calls():
    async def go():
        f = Fake(); e = mk(f); inc = new(e)
        await asyncio.sleep(0.05)
        e.ack(inc.id, "+919800000001")
        await asyncio.sleep(0.6)
        assert not [x for x in f.log if x[0] == "call"]
        assert inc.status == "acknowledged"
    asyncio.run(go())


def test_cancel_sends_all_clear_and_stops():
    async def go():
        f = Fake(); e = mk(f); inc = new(e)
        await asyncio.sleep(0.05)
        await e.cancel(inc.id)
        await asyncio.sleep(0.6)
        assert not [x for x in f.log if x[0] == "call"]
        assert sum("False alarm" in x[2] for x in f.log if x[0] == "sms") == 3
    asyncio.run(go())


def test_failed_send_does_not_stop_escalation():
    class Flaky(Fake):
        async def call(self, to, say):
            if to.endswith("1"):
                raise RuntimeError("boom")
            await super().call(to, say)

    async def go():
        f = Flaky(); e = mk(f); inc = new(e)
        await asyncio.sleep(0.7)
        assert len([x for x in f.log if x[0] == "call"]) == 2
        assert any("call_failed" in ev["event"] for ev in inc.events)
    asyncio.run(go())


def test_rejects_bad_phone():
    async def go():
        e = mk(Fake())
        try:
            e.create(user_name="x", lat=0, lon=0, accuracy=0, probability=1,
                     contacts=[Contact("a", "98000")], medical={})
            assert False
        except ValueError:
            pass
    asyncio.run(go())


def test_api_flow_and_auth():
    app = create_app(Fake(), [(0, "sms", "all"), (60, "call", 0)], api_key="k")
    with TestClient(app) as c:
        body = {"user_name": "Nistal", "lat": 9.9, "lon": 76.3, "probability": 0.9,
                "contacts": [{"name": "A", "phone": "+919800000001"}]}
        assert c.post("/v1/incidents", json=body).status_code == 401
        r = c.post("/v1/incidents", json=body, headers={"x-api-key": "k"})
        assert r.status_code == 201
        iid = r.json()["id"]
        assert c.get(f"/t/{iid}").status_code == 200
        assert c.get(f"/v1/incidents/{iid}/public").json()["name"] == "Nistal"
        assert c.post(f"/v1/incidents/{iid}/cancel", headers={"x-api-key": "k"}).json()["status"] == "cancelled"
        bad = dict(body, contacts=[{"name": "A", "phone": "123"}])
        assert c.post("/v1/incidents", json=bad, headers={"x-api-key": "k"}).status_code == 422
