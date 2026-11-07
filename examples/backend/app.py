"""CrashGuard backend: incident intake, contact escalation, live tracking page.

Run:  uvicorn app:app --host 0.0.0.0 --port 8000
Env:  CRASHGUARD_API_KEY (required in prod), BASE_URL,
      TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM (else console notifier)
State is in-memory: swap `Escalator.incidents` for Redis/Postgres before real use.
"""
import hmac
import html
import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from escalation import (Contact, ConsoleNotifier, Escalator, TwilioNotifier)


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    phone: str


class IncidentIn(BaseModel):
    user_name: str = Field(min_length=1, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy: float = 0
    probability: float = Field(ge=0, le=1)
    contacts: list[ContactIn] = Field(min_length=1, max_length=5)
    medical: dict = {}


class AckIn(BaseModel):
    phone: str


class LocIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def make_notifier():
    sid, tok, frm = (os.getenv(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"))
    return TwilioNotifier(sid, tok, frm) if sid and tok and frm else ConsoleNotifier()


def create_app(notifier=None, policy=None, api_key: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="CrashGuard", version="0.1.0")
    esc = Escalator(notifier or make_notifier(), os.getenv("BASE_URL", "http://localhost:8000"), policy)
    key = api_key if api_key is not None else os.getenv("CRASHGUARD_API_KEY", "")

    def auth(x_api_key: str = Header(default="")):
        if key and not hmac.compare_digest(x_api_key, key):
            raise HTTPException(401, "bad api key")

    def get(iid):
        if iid not in esc.incidents:
            raise HTTPException(404, "unknown incident")
        return esc.incidents[iid]

    @app.post("/v1/incidents", dependencies=[Depends(auth)], status_code=201)
    async def create(body: IncidentIn):
        try:
            inc = esc.create(user_name=body.user_name, lat=body.lat, lon=body.lon,
                             accuracy=body.accuracy, probability=body.probability,
                             contacts=[Contact(c.name, c.phone) for c in body.contacts],
                             medical=body.medical)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {"id": inc.id, "track_url": f"{esc.base_url}/t/{inc.id}"}

    @app.get("/v1/incidents/{iid}", dependencies=[Depends(auth)])
    async def status(iid: str):
        i = get(iid)
        return {"id": i.id, "status": i.status, "acked_by": i.acked_by, "events": i.events}

    @app.post("/v1/incidents/{iid}/cancel", dependencies=[Depends(auth)])
    async def cancel(iid: str):
        get(iid)
        return {"status": (await esc.cancel(iid)).status}

    @app.post("/v1/incidents/{iid}/location", dependencies=[Depends(auth)])
    async def location(iid: str, body: LocIn):
        get(iid)
        esc.update_location(iid, body.lat, body.lon)
        return {"ok": True}

    @app.post("/v1/incidents/{iid}/ack")   # contacts ack from the tracking page; id is the secret
    async def ack(iid: str, body: AckIn):
        get(iid)
        return {"status": esc.ack(iid, body.phone).status}

    @app.get("/v1/incidents/{iid}/public")
    async def public(iid: str):
        i = get(iid)
        return {"name": i.user_name, "lat": i.lat, "lon": i.lon, "status": i.status,
                "medical": i.medical}

    @app.get("/t/{iid}", response_class=HTMLResponse)
    async def track(iid: str):
        i = get(iid)
        n = html.escape(i.user_name)
        return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>CrashGuard - {n}</title>
<body style="font-family:system-ui;max-width:520px;margin:2rem auto;padding:0 1rem">
<h2>&#9888; {n} may have been in a crash</h2>
<p id=s>loading...</p>
<p><a id=m target=_blank>Open in Maps</a></p>
<button onclick="ack()" style="font-size:1.1rem;padding:.7rem 1rem">I'm responding / I've reached them</button>
<script>
const id="{i.id}";
async function load(){{const r=await (await fetch('/v1/incidents/'+id+'/public')).json();
 document.getElementById('s').textContent='Status: '+r.status+' | '+r.lat.toFixed(5)+', '+r.lon.toFixed(5);
 document.getElementById('m').href='https://maps.google.com/?q='+r.lat+','+r.lon;}}
async function ack(){{const p=prompt('Your phone number (+countrycode...)');if(!p)return;
 await fetch('/v1/incidents/'+id+'/ack',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{phone:p}})}});load();}}
load();setInterval(load,5000);
</script>"""

    app.state.escalator = esc
    return app


app = create_app()
