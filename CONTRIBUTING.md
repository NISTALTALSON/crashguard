# Contributing to CrashGuard

Thanks for helping make crash detection open. Highest-impact contributions first:

1. **Real data** in the [event format](docs/DATA_FORMAT.md): validate with `python tools/validate_event.py your_event.json`, then open a PR adding it under `data/contributed/` (or an issue if the files are large). No location, no personal info, and **never stage dangerous events**.
2. **Field evaluation.** Run the model on your own rides/drives and report measured false alarms and misses (issue template: device, mount, vehicle, hours, outcomes).
3. **Ports.** Swift, Dart/Flutter, Rust, C/C++ for microcontrollers (ESP32, nRF), Go, Java. Prove parity with `ml/model/parity.json` (see [SPEC](docs/SPEC.md#9-porting-checklist)) and add your port under its own folder with a test.
4. **Simulator scenarios.** Add a function in `ml/simulate.py`, register it in `SCENARIOS`, run `ml/train.py`, and include the new `REPORT.md` rows in your PR. Say what real-world evidence the parameters come from.
5. **Model improvements.** Must beat the current scenario-held-out numbers in `ml/REPORT.md` without raising false alarms.

## Rules
- Keep every port's outputs identical; update `parity.json` and all ports together when features change (`ml/train.py` regenerates the vectors and models).
- Be honest in numbers: report held-out results, say what is simulated.
- Tests must pass: `pytest tests examples/backend`, `cd js && npm test`.
- Do not test with real emergency calls.

By contributing you agree your contribution is released under the MIT license (data under CC BY 4.0 if you say so in the PR).
