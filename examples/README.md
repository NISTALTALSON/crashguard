# Examples (not the product)

CrashGuard is the **model and spec**. These folders show one way to wrap it. Take what's useful.

- `android/`: Kotlin core + phone app + Wear OS app (foreground sensing, countdown, SMS/112, event logger). **Written without a compiler available; not yet compiled or device-tested.** The CI job `android-core` is the first check.
- `backend/`: FastAPI contact-escalation service (SMS, then calls contacts in order until one acknowledges, live-location page, Twilio or console). 6 tests pass. In-memory state; swap in a database before real use. A server cannot place a 112 call for the user; the device has to.

The Android app saves trigger events with their raw windows and labels them `escalated` / `cancelled_by_user`. Those are **not** ground truth; relabel them to `crash` / `not_crash` before contributing (see docs/DATA_FORMAT.md).
