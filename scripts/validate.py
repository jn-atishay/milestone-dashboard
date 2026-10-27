"""Checks data.json before the routine commits it. Exit code 1 blocks the commit.
Run: python3 scripts/validate.py"""
import json, re, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
cfg = json.loads((root / "config.json").read_text())
raw = (root / "data.json").read_text()
errors = []
try:
    d = json.loads(raw)
except Exception as e:
    print("data.json is not valid JSON:", e); sys.exit(1)

need = ["SNAPSHOT", "PACE", "DAILY", "POPUP", "CLAIMS", "WEEKLY", "COHORTS", "COHORT_LABELS", "QUALITY",
        "FX", "Q_FUNNEL", "Q_BT", "Q_VOL", "REFERRERS_RAW", "TRENDS", "GOLD", "CAMPAIGNS", "notes"]
for k in need:
    if k not in d: errors.append(f"missing key {k}")

if not errors:
    refs = d["REFERRERS_RAW"]
    if not refs: errors.append("REFERRERS_RAW is empty")
    for r in refs:
        if len(r) != 10: errors.append(f"referrer row has {len(r)} fields: {r[:2]}"); break
        if not all(isinstance(r[i], int) for i in (0, 5, 6, 7)): errors.append(f"non-integer counts in row {r[0]}"); break
        if not (r[5] >= r[6] >= r[7] >= 0): errors.append(f"signups >= onboardings >= activations broken for {r[0]}"); break
    excluded = set(cfg["always_excluded_referrers"] + cfg["flagged_referrers"])
    leaked = [r[0] for r in refs if r[0] in excluded]
    if leaked: errors.append(f"excluded referrers present: {leaked}")
    if not cfg.get("show_customer_names") and any(r[1] for r in refs):
        errors.append("customer names present but show_customer_names is false")
    # Personal data guard: no emails or Indian mobile numbers anywhere in the file
    if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", raw): errors.append("an email address is present in data.json")
    if re.search(r"(?:\+?91[\s-]?)?[6-9]\d{9}\b", raw): errors.append("something that looks like a phone number is present in data.json")

    p = d["PACE"]
    for k in ["months", "sepToDate", "sepDaily", "target", "stretchPlus", "monthName", "monthShort", "daysInMonth"]:
        if k not in p: errors.append(f"PACE.{k} missing")
    if "sepDaily" in p and "sepToDate" in p and abs(sum(p["sepDaily"]) - p["sepToDate"]) > max(3, 0.02 * p["sepToDate"]):
        errors.append(f"PACE.sepDaily sums to {sum(p['sepDaily'])} but sepToDate is {p['sepToDate']}")
    if d["SNAPSHOT"].get("fullDays") and len(p.get("sepDaily", [])) != d["SNAPSHOT"]["fullDays"]:
        errors.append("PACE.sepDaily length does not match SNAPSHOT.fullDays")
    if len(p.get("months", [])) != 3: errors.append("PACE.months should have the previous three months")
    if len(d["COHORTS"]) != 9: errors.append(f"COHORTS should have 9 rows, has {len(d['COHORTS'])}")

    t = d["TRENDS"]
    if len(t) != 13: errors.append(f"TRENDS should have 13 months, has {len(t)}")
    for row in t:
        if not all(isinstance(row.get(k), int) for k in ("signups", "referrers", "refOnboardings", "refActivations", "allOnboardings", "transactors")):
            errors.append(f"TRENDS row {row.get('ym')} has non-integer counts"); break

    g = d["GOLD"]
    f = g.get("funnel", {})
    if not all(isinstance(f.get(k), int) for k in ("signups", "referrers", "onboarded", "achieved", "claimed")):
        errors.append("GOLD.funnel counts must be integers")
    elif not (f["signups"] >= f["onboarded"] >= f["achieved"] >= 0): errors.append("GOLD.funnel signups >= onboarded >= achieved broken")
    if not isinstance(g.get("pinned", {}).get("n"), int) or g["pinned"]["n"] <= 0: errors.append("GOLD.pinned.n missing")
    if not g.get("daily"): errors.append("GOLD.daily is empty")
    if not g.get("weekly"): errors.append("GOLD.weekly is empty")

    c = d["CAMPAIGNS"]
    want = {x["id"] for x in cfg.get("campaign_history", [])}
    have = {x.get("id") for x in c}
    if want - have: errors.append(f"CAMPAIGNS missing ids {sorted(want - have)}")

    for k in ["pace", "daily", "ladder", "cohorts", "mix", "weeklyQuality", "claims", "popupHeader", "popup", "referrers", "refereeQuality",
              "qualityHeader", "qualityWindow", "overview", "gold", "campaigns"]:
        if k not in d["notes"]: errors.append(f"notes.{k} missing")
    if "—" in raw: errors.append("em dash found in notes; use plain punctuation")

if errors:
    print("VALIDATION FAILED"); [print(" -", e) for e in errors]; sys.exit(1)
print(f"OK: {len(d['REFERRERS_RAW'])} referrers, {sum(r[5] for r in d['REFERRERS_RAW'])} signups, "
      f"gold coin {d['GOLD']['funnel']['referrers']} referrers / {d['GOLD']['funnel']['claimed']} claimed, as of {d['SNAPSHOT']['asOf']}")
