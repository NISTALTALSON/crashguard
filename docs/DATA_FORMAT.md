# Event data format (for contributing real data)

One JSON file per event. A validator lives in `tools/validate_event.py`.

```json
{
  "schema_version": 1,
  "label": "crash",                    // "crash" | "not_crash"  (ground truth, not "user cancelled")
  "scenario": "motorcycle low-side",   // free text, e.g. "phone dropped in car", "pothole at 40 km/h"
  "vehicle": "motorcycle",             // car | motorcycle | scooter | bicycle | auto_rickshaw | pedestrian | none | other
  "mount": "jacket_pocket",            // trouser_pocket | jacket_pocket | handlebar | helmet | wrist | bag | cabin_mount | other
  "device": { "model": "Pixel 7", "accel_range_g": 8, "gyro_range_dps": 2000 },
  "sample_rate_hz": 50,
  "acc": [[0.01, 0.02, 1.0], "... 128 rows ..."],   // g, gravity included, 50 Hz peak-hold (see SPEC.md)
  "gyr": [[0.0, 0.0, 0.0], "... 128 rows ..."],      // rad/s
  "gps_ok": true,
  "v_pre": 11.2,                       // m/s, see SPEC.md section 5
  "v_post": 0.3,
  "source": "dashcam-verified",        // how the label was established
  "consent": true                      // contributor owns the data and agrees to release it under CC BY 4.0 / MIT
}
```
**Never include** location, names, phone numbers, timestamps tied to a person, or media. The impact should sit near sample 40.

## Ethics
- Do **not** stage dangerous events. Good sources: normal rides with real potholes/bumps/drops (`not_crash`), real incidents recorded by consenting riders with a verifying dashcam/helmet cam, telematics owners' anonymised data.
- Label `crash` only when you are sure.
