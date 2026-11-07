"""Train + evaluate the impact classifier and export it for Android / Wear OS / JS / Python.

Pipeline: simulate (on real HAR texture) -> trigger gate (peak >= 3.5 g) -> 21 features
-> MLP -> JSON weights read by the Kotlin and JS cores.

Honest evaluation: models are scored with GROUP K-FOLD BY SCENARIO, i.e. every test
event comes from a scenario TYPE the model never saw during training. That is far
harder (and closer to the real world, where new situations keep showing up) than a
random split. The random-split number is reported too, only for comparison.

Outputs: model/crash_model.json, model/parity.json, ../examples/android/shared-assets/, ../crashguard/data/,
         ../js/crash_model.json, REPORT.md
"""
import json
import shutil
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

import simulate as sim
from features import FEATURES, extract

HERE = Path(__file__).parent
OUT = HERE / "model"
OUT.mkdir(exist_ok=True)
TARGET_FPR = 0.01
CONFIGS = [((32, 16), 1e-3), ((64, 32), 1e-3), ((64, 32), 1e-2), ((64, 32, 16), 1e-2)]


def fit(X, y, hidden=(64, 32), alpha=1e-2, seed=0):
    sc = StandardScaler().fit(X)
    clf = MLPClassifier(hidden, activation="relu", alpha=alpha, max_iter=500,
                        early_stopping=True, n_iter_no_change=15, random_state=seed)
    clf.fit(sc.transform(X), y)
    return sc, clf


def proba(sc, clf, X):
    return clf.predict_proba(sc.transform(X))[:, 1]


def oof(X, y, groups, hidden, alpha, folds=6):
    p = np.zeros(len(y))
    for tr, te in GroupKFold(folds).split(X, y, groups):
        sc, clf = fit(X[tr], y[tr], hidden, alpha, seed=3)
        p[te] = proba(sc, clf, X[te])
    return p


def macro_correct(p, y, groups, thr=0.5):
    return float(np.mean([((p[groups == g] >= thr) == (y[groups == g] == 1)).mean()
                          for g in np.unique(groups)]))


def pick_threshold(p, y, fpr=TARGET_FPR):
    neg = np.sort(p[y == 0])
    return float(max(0.5, neg[int(np.ceil((1 - fpr) * len(neg))) - 1]))


def forward(model, x):
    h = (np.asarray(x) - model["mean"]) / model["std"]
    for i, (W, b) in enumerate(zip(model["weights"], model["biases"])):
        h = h @ np.asarray(W) + np.asarray(b)
        h = np.maximum(h, 0) if i < len(model["weights"]) - 1 else 1 / (1 + np.exp(-h))
    return float(h[0])


def main():
    print("simulating events ...", flush=True)
    X, y, scn, trig = sim.build_dataset(per_scenario=1000)
    names = list(sim.SCENARIOS)

    real = sim.total_acc_windows()                       # REAL data
    real_rate = float(np.mean(np.linalg.norm(real, axis=2).max(axis=1) >= sim.TRIGGER_G))
    trig_stats = {n: float(trig[scn == n].mean()) for n in names}

    Xt, yt, st = X[trig], y[trig], scn[trig]

    # ---- model selection by scenario-held-out score
    results = []
    for hidden, alpha in CONFIGS:
        p = oof(Xt, yt, st, hidden, alpha)
        results.append((macro_correct(p, yt, st), hidden, alpha, p))
        print(f"config {hidden} a={alpha}: macro held-out score {results[-1][0]:.4f}", flush=True)
    score, hidden, alpha, p_oof = max(results, key=lambda r: r[0])
    thr = pick_threshold(p_oof, yt)
    pred = p_oof >= thr
    recall, fpr = float(pred[yt == 1].mean()), float(pred[yt == 0].mean())
    auc = roc_auc_score(yt, p_oof)
    per_oof = {n: float(pred[st == n].mean()) for n in names}

    # ---- same architecture on a random split, for comparison only
    Xtr, Xte, ytr, yte = train_test_split(Xt, yt, test_size=0.25, stratify=yt, random_state=1)
    s2, c2 = fit(Xtr, ytr, hidden, alpha)
    pr = proba(s2, c2, Xte) >= thr
    rs_recall, rs_fpr = float(pr[yte == 1].mean()), float(pr[yte == 0].mean())

    # ---- final model on everything
    scA, clfA = fit(Xt, yt, hidden, alpha)
    model = dict(
        version=2, trigger_g=sim.TRIGGER_G, threshold=thr, features=FEATURES,
        mean=scA.mean_.tolist(), std=scA.scale_.tolist(),
        weights=[w.tolist() for w in clfA.coefs_], biases=[b.tolist() for b in clfA.intercepts_],
    )
    blob = json.dumps(model)
    (OUT / "crash_model.json").write_text(blob)
    for dest in (HERE.parent / "examples" / "android" / "shared-assets", HERE.parent / "js", HERE.parent / "crashguard" / "data"):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "crash_model.json").write_text(blob)

    parity = []
    for i, nm in enumerate(["car_frontal", "moto_highside", "scooter_fall", "phone_drop", "pothole",
                            "door_slam", "phone_drop_in_vehicle", "moto_lowside", "pedestrian_hit",
                            "sustained_ride"]):
        acc, gyr, m = sim.render(nm, np.random.default_rng(1000 + i))
        f = extract(acc, gyr, m["vpre"], m["vpost"], m["gps_ok"])
        parity.append(dict(name=nm, acc=np.round(acc, 6).tolist(), gyr=np.round(gyr, 6).tolist(),
                           v_pre=m["vpre"], v_post=m["vpost"], gps_ok=m["gps_ok"],
                           features=f.tolist(), probability=forward(model, f)))
    (OUT / "parity.json").write_text(json.dumps(parity))
    shutil.copy(OUT / "parity.json", HERE.parent / "js" / "parity.json")
    assert abs(forward(model, Xt[0]) - proba(scA, clfA, Xt[:1])[0]) < 1e-6, "export mismatch"

    L = ["# Training report (auto-generated by `ml/train.py`)", "",
         "> **Read this first.** Crashes and hard negatives are *simulated* (physics model on top of "
         "real UCI HAR sensor noise); no public labelled dataset of real phone-sensor crashes exists. "
         "Numbers below measure how well the classifier separates scenario families under my modelling "
         "assumptions. They are **not** a real-world accuracy claim. The app records labelled real "
         "events so the model can be retrained on field data.", "",
         f"- Simulated events: {len(X)} over {len(names)} scenario types "
         f"({int(y.sum())} crash / {int((1 - y).sum())} non-crash); {int(trig.sum())} pass the "
         f"{sim.TRIGGER_G} g trigger gate",
         f"- **Real data:** {len(real)} real HAR windows ({len(real) * 2.56 / 3600:.1f} h of everyday "
         f"activity): natural trigger rate {real_rate * 100:.3f}% ({int(real_rate * len(real))} windows)",
         f"- Chosen architecture: MLP {hidden}, L2 alpha={alpha} (best of {len(CONFIGS)} by scenario-held-out score)",
         f"- **Scenario-held-out (6-fold, test scenarios never seen in training):** AUC **{auc:.4f}**, "
         f"crash recall **{recall * 100:.1f}%**, false-alarm rate **{fpr * 100:.2f}%** at threshold {thr:.3f} "
         f"(threshold set for <= {TARGET_FPR * 100:.0f}% FPR on those held-out predictions)",
         f"- Random split (same scenarios in train and test; optimistic, for comparison only): "
         f"recall {rs_recall * 100:.1f}%, false-alarm {rs_fpr * 100:.2f}%",
         "", "| scenario | label | passes trigger | held-out: flagged as crash |", "|---|---|---|---|"]
    for n in names:
        lab = "CRASH" if sim.SCENARIOS[n][1] else "no crash"
        L.append(f"| {n} | {lab} | {trig_stats[n] * 100:.0f}% | {per_oof[n] * 100:.0f}% |")
    L += ["", "For CRASH rows high is good; for no-crash rows low is good. 'passes trigger' below 100% for "
          "crashes means the +-8/16 g phone accelerometer never crossed the gate (a real hardware limit).", ""]
    (HERE / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
