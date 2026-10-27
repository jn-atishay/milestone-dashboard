#!/usr/bin/env python3
"""Rebuilds data.json from Metabase and Mixpanel.

    python3 scripts/refresh.py               run every query, rebuild data.json (keeps the current notes), write raw/summary.json
    python3 scripts/refresh.py --notes-only  merge raw/notes.json into data.json without querying anything
    python3 scripts/refresh.py --force-quality   also rerun the once-a-day referee quality query

Credentials are read at run time from environment variables (METABASE_URL, METABASE_API_KEY, MIXPANEL_USER,
MIXPANEL_SECRET, MIXPANEL_PROJECT) or, failing that, from the Claude Desktop MCP config on this Mac. Nothing is
stored in the repository. If anything fails the script exits non-zero and data.json is left untouched.
"""
import base64
import datetime as dt
import json
import os
import pathlib
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
IST = ZoneInfo("Asia/Kolkata")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# ----------------------------------------------------------------------------------------------------------------
# Connections
# ----------------------------------------------------------------------------------------------------------------
def load_creds():
    env = os.environ
    creds = {
        "metabase_url": env.get("METABASE_URL"), "metabase_key": env.get("METABASE_API_KEY"),
        "mp_user": env.get("MIXPANEL_USER"), "mp_secret": env.get("MIXPANEL_SECRET"), "mp_project": env.get("MIXPANEL_PROJECT"),
    }
    if all(creds.values()):
        return creds
    cfg_path = pathlib.Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if not cfg_path.exists():
        sys.exit("No credentials: set METABASE_URL, METABASE_API_KEY, MIXPANEL_USER, MIXPANEL_SECRET, MIXPANEL_PROJECT or install the Metabase and Mixpanel MCP servers in Claude Desktop.")
    servers = json.loads(cfg_path.read_text()).get("mcpServers", {})
    mb = servers.get("metabase", {}).get("env", {})
    mp_args = servers.get("mcp-mixpanel", {}).get("args", [])
    creds["metabase_url"] = creds["metabase_url"] or mb.get("METABASE_URL")
    creds["metabase_key"] = creds["metabase_key"] or mb.get("METABASE_API_KEY")
    if len(mp_args) >= 3:
        creds["mp_user"] = creds["mp_user"] or mp_args[-3]
        creds["mp_secret"] = creds["mp_secret"] or mp_args[-2]
        creds["mp_project"] = creds["mp_project"] or mp_args[-1]
    missing = [k for k, v in creds.items() if not v]
    if missing:
        sys.exit(f"Missing credentials: {missing}")
    return creds


def ssl_context():
    """Default trust store plus the macOS system keychain, which carries any corporate root the network injects."""
    ctx = ssl.create_default_context()
    try:
        pem = subprocess.run(["security", "find-certificate", "-a", "-p", "/Library/Keychains/System.keychain",
                              "/System/Library/Keychains/SystemRootCertificates.keychain"], capture_output=True, text=True, timeout=30).stdout
        if "BEGIN CERTIFICATE" in pem:
            with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
                f.write(pem)
            ctx.load_verify_locations(cafile=f.name)
            os.unlink(f.name)
    except Exception:
        pass
    return ctx


class Sources:
    def __init__(self, creds):
        self.c = creds
        self.ctx = ssl_context()

    def _get(self, req, timeout):
        last = None
        for attempt in range(2):  # retry once, as the routine always did
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                    return json.load(r)
            except Exception as e:  # noqa: BLE001
                last = e
        raise RuntimeError(f"{req.full_url.split('?')[0]}: {last}")

    def metabase(self, sql, database_id):
        body = json.dumps({"database": database_id, "type": "native", "native": {"query": sql}}).encode()
        req = urllib.request.Request(self.c["metabase_url"].rstrip("/") + "/api/dataset", data=body,
                                     headers={"Content-Type": "application/json", "x-api-key": self.c["metabase_key"]})
        r = self._get(req, 300)
        if r.get("status") != "completed":
            raise RuntimeError(f"Metabase: {r.get('error') or r}")
        return r["data"]["rows"]

    def mixpanel_unique(self, event, where, frm, to):
        days = (to - frm).days + 1
        q = urllib.parse.urlencode({"project_id": self.c["mp_project"], "event": event, "from_date": frm.isoformat(), "to_date": to.isoformat(),
                                    "type": "unique", "interval": days, "where": where})
        auth = base64.b64encode(f"{self.c['mp_user']}:{self.c['mp_secret']}".encode()).decode()
        req = urllib.request.Request(f"https://mixpanel.com/api/query/segmentation?{q}", headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
        r = self._get(req, 120)
        vals = r["data"]["values"].get(event, {})
        return int(sum(vals.values()))


# ----------------------------------------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------------------------------------
def d(s):
    return dt.date.fromisoformat(str(s)[:10])


def lbl(s):
    x = d(s)
    return f"{x.day} {MONTHS[x.month - 1]}"


def num(x, default=0):
    if x is None or x == "":
        return default
    s = str(x)
    return float(s) if "." in s else int(s)


def pct(a, b, digits=1):
    return round(100.0 * a / b, digits) if b else None


def fill(sql, cfg):
    always = ",".join(str(x) for x in cfg["always_excluded_referrers"])
    excluded = ",".join(str(x) for x in cfg["always_excluded_referrers"] + cfg["flagged_referrers"])
    reps = {
        "{{EXCLUDED}}": excluded, "{{ALWAYS_EXCLUDED}}": always, "{{CAMPAIGN_ID}}": str(cfg["campaign_id"]),
        "{{CAMPAIGN_START}}": cfg["campaign_start"], "{{SHOW_NAMES}}": "true" if cfg.get("show_customer_names") else "false",
        "{{GOLD_CAMPAIGN_ID}}": str(cfg["gold_coin"]["campaign_id"]), "{{GOLD_START}}": cfg["gold_coin"]["start"],
        "{{CAMPAIGN_HISTORY_IDS}}": ",".join(str(c["id"]) for c in cfg["campaign_history"]),
    }
    for k, v in reps.items():
        sql = sql.replace(k, v)
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def query(src, cfg, name):
    return src.metabase(fill((ROOT / "queries" / name).read_text(), cfg), cfg["metabase_database_id"])


# ----------------------------------------------------------------------------------------------------------------
# Block builders
# ----------------------------------------------------------------------------------------------------------------
def build_pace(rows, cfg, today):
    days = {r[1]: int(r[2]) for r in rows if r[0] == "day"}
    daily = [days.get(today.replace(day=i).isoformat(), 0) for i in range(1, today.day)]
    months = [{"month": MONTHS[int(r[1][5:7]) - 1], "firstN": int(r[3]), "full": int(r[2])} for r in rows if r[0] == "month"]
    tgt = cfg["targets"].get(today.strftime("%Y-%m")) or {}
    nxt = (today.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return {
        "ym": today.strftime("%Y-%m"), "target": tgt.get("target"), "stretchPlus": tgt.get("stretchPlus"), "months": months,
        "sepDaily": daily, "sepToDate": sum(daily), "todaySoFar": next((int(r[2]) for r in rows if r[0] == "today"), 0),
        "monthName": MONTH_NAMES[today.month - 1], "monthShort": MONTHS[today.month - 1], "daysInMonth": (nxt - dt.timedelta(days=1)).day,
    }


def build_campaign(rows):
    g = lambda k: [r for r in rows if r[0] == k]
    daily = [{"day": lbl(r[1]), "dow": r[2], "signups": num(r[3]), "referrers": num(r[4]), "onboardings": num(r[5]), "activations": num(r[6]), "claims": num(r[7])} for r in g("daily")]
    quality = [{"week": lbl(r[1]), "signups": num(r[3]), "ob1d": num(r[4]), "ob7d": num(r[5]), "obSoFar": num(r[6]), "actOfOb": num(r[7]), "medianDays": num(r[8])} for r in g("quality")]
    weekly = [{"week": lbl(r[1]), "period": r[2], "signups": num(r[3]), "referrers": num(r[4]), "perRef": float(r[5])} for r in g("weekly")]
    claims = sorted([{"reward": r[1], "threshold": int(r[3]), "status": "Claimed" if r[2] == "CLAIMED" else "Forfeited", "count": int(r[4]),
                      "first": lbl(r[5]), "last": lbl(r[6]), "avgAchieved": num(r[7])} for r in g("claims")], key=lambda x: (x["threshold"], x["status"]))
    top24h = sorted([{"id": int(r[1]), "signups": int(r[3])} for r in g("top24h")], key=lambda x: -x["signups"])
    return daily, quality, weekly, claims, top24h


COHORT_LABELS = [("1", "Activated before month start", 0), ("1a", "never referred before", 1), ("1b", "referred in the past", 1),
                 ("1.1", "transacted this month", 1), ("1.2", "recently dormant (txn in prev 3 mo)", 1), ("1.3", "dormant (no txn 3+ mo)", 1),
                 ("2", "New activations this month (M0)", 0), ("3", "Not activated, onboarded this month", 0), ("4", "Not activated, old onboarder", 0)]


def build_cohorts(rows):
    by = {str(r[0]): r for r in rows}
    out = []
    for cid, label, indent in COHORT_LABELS:
        r = by.get(cid)
        if r is None:
            out.append({"id": cid, "label": label, "indent": indent, "base": 0, "refNow": 0, "rateNow": 0, "refPrev": 0, "ratePrev": 0, "delta": None})
            continue
        base, ref_now, rate_now, ref_prev, rate_prev = int(r[1]), int(r[2]), float(r[3]), int(r[4] or 0), float(r[5] or 0)
        out.append({"id": cid, "label": label, "indent": indent, "base": base, "refNow": ref_now, "rateNow": rate_now, "refPrev": ref_prev, "ratePrev": rate_prev,
                    "delta": round((rate_now - rate_prev) / rate_prev * 100, 1) if rate_prev else None})
    return out


def build_quality(rows, today):
    prev_m = (today.replace(day=1) - dt.timedelta(days=1))
    src = {"prev": f"{MONTHS[prev_m.month - 1]} referrals", "now_single": f"{MONTHS[today.month - 1]}, single-signup referrers", "now_multi": f"{MONTHS[today.month - 1]}, 2+ signup referrers"}
    f = {r[1]: r for r in rows if r[0] == "funnel"}
    funnel = [{"src": src[k], "n": num(f[k][2]), "ob1d": num(f[k][3]), "ob7d": num(f[k][4]), "matureN": num(f[k][5]), "act10": num(f[k][6]), "medianFirstInr": num(f[k][7])}
              for k in ["prev", "now_single", "now_multi"] if k in f]

    def two(group, names, codes, key):
        rows_ = {r[1]: r for r in rows if r[0] == group}
        out = []
        for name, code in zip(names, codes):
            p, c = rows_.get("prev:" + code), rows_.get("now:" + code)
            val = lambda r, i: None if r is None else num(r[i])
            act = lambda r: None if r is None or num(r[4]) == 0 else num(r[5])
            out.append({key: name, "preN": val(p, 2), "preShare": val(p, 3), "preAct": act(p), "cN": val(c, 2), "cShare": val(c, 3), "cAct": act(c)})
        return out

    bt = two("bt", ["Freelancer", "Sole prop", "Company", "LLP", "Partnership", "HUF"],
             ["FREELANCER", "SOLE_PROPRIETORSHIP", "COMPANY", "LIMITED_LIABILITY_PARTNERSHIP", "PARTNERSHIP", "HINDU_UNDIVIDED_FAMILY"], "bt")
    vol = two("vol", ["Not stated", "Under $10K a month", "$10K to 20K", "$20K to 50K", "$50K and above"], ["0", "1", "2", "3", "4"], "vol")
    fx = round(float(next(r[2] for r in rows if r[0] == "fx")))
    return funnel, bt, vol, fx


def build_trends(rows, today):
    out = []
    for r in rows:
        ym = r[0]
        signups, referrers, first_timers, ref_ob, ref_act, all_ob, transactors, sharers = (int(x) for x in r[1:9])
        y, m = int(ym[:4]), int(ym[5:7])
        out.append({"ym": ym, "month": f"{MONTHS[m - 1]} {str(y)[2:]}", "signups": signups, "referrers": referrers, "firstTimers": first_timers,
                    "refOnboardings": ref_ob, "refActivations": ref_act, "allOnboardings": all_ob, "transactors": transactors, "sharers": sharers,
                    "shareRate": pct(sharers, transactors, 2), "refShare": pct(ref_ob, all_ob, 1), "partial": ym == today.strftime("%Y-%m")})
    return out


def build_gold(rows, cfg, today, src):
    gc = cfg["gold_coin"]
    start = d(gc["start"])
    g = lambda k: [r for r in rows if r[0] == k]
    daily = [{"day": lbl(r[1]), "date": r[1], "signups": num(r[2]), "referrers": num(r[3]), "onboarded": num(r[4]), "achieved": num(r[5]), "partial": d(r[1]) == today} for r in g("day")]
    f = g("funnel")[0]
    p = g("pinned")[0]
    weekly = []
    for r in g("week"):
        ws = d(r[1])
        transactors = num(r[6])
        weekly.append({"week": lbl(r[1]), "ws": r[1], "post": ws >= start, "partial": ws + dt.timedelta(days=7) > today, "referrers": num(r[2]), "signups": num(r[3]),
                       "onboarded": num(r[4]), "achieved": num(r[5]), "transactors": transactors, "shareRate": pct(num(r[2]), transactors, 2)})
    yesterday = today - dt.timedelta(days=1)
    mp = {"widgetUsers": None, "claimCta": None, "claimConfirm": None}
    try:
        t = gc["widget_type"]
        mp["widgetUsers"] = src.mixpanel_unique("referral_widget_loaded", f'properties["type"] == "{t}"', start, yesterday)
        mp["claimCta"] = src.mixpanel_unique("referral_milestone_claim_cta_click", f'properties["type"] == "{t}"', start, yesterday)
        mp["claimConfirm"] = src.mixpanel_unique("referral_milestone_claim_confirm_click", f'properties["type"] == "{t}"', start, yesterday)
    except Exception as e:  # noqa: BLE001
        mp["error"] = str(e)[:200]
    return {
        "campaignId": gc["campaign_id"], "label": gc["label"], "reward": gc["reward"], "start": gc["start"], "startLabel": lbl(gc["start"]),
        "dayN": (today - start).days + 1, "window": f"{lbl(gc['start'])} to {lbl(yesterday.isoformat())}",
        "pinned": {"n": num(p[2]), "date": lbl(p[3]) if p[3] else None, "active90d": num(p[4]), "referredBefore": num(p[5])},
        "funnel": {"signups": num(f[2]), "referrers": num(f[3]), "onboarded": num(f[4]), "achieved": num(f[5]), "claimed": num(f[6]), "firstEverReferrers": num(f[7])},
        "daily": daily, "weekly": weekly,
        "claims": sorted([{"date": lbl(r[1]), "id": int(r[2]), "status": r[3], "source": r[4]} for r in g("claims")], key=lambda x: d(next(r[1] for r in g("claims") if int(r[2]) == x["id"]))),
        "daysToFirst": sorted([{"days": int(r[1]), "n": int(r[2])} for r in g("days_to_first")], key=lambda x: x["days"]),
        **mp,
    }


def build_campaigns(rows, cfg, today):
    meta = {c["id"]: c for c in cfg["campaign_history"]}
    out = []
    for r in rows:
        cid, name, active, created_d, first_d, last_d, signups, referrers, onboarded, achieved, claimed, gifts = r
        start = d(created_d)
        last = d(last_d) if last_d else None
        live = bool(active) and last is not None and (today - last).days <= 3
        end = today if live else (last or start)
        days = max(1, (end - start).days + 1)
        m = meta.get(cid, {})
        out.append({"id": cid, "name": name, "label": m.get("label", name), "gift": m.get("gift", gifts or ""), "start": created_d, "startLabel": f"{start.day} {MONTHS[start.month - 1]} {str(start.year)[2:]}",
                    "end": None if live else end.isoformat(), "endLabel": "live" if live else f"{end.day} {MONTHS[end.month - 1]} {str(end.year)[2:]}", "live": live, "days": days,
                    "signups": signups, "referrers": referrers, "onboarded": onboarded, "achieved": achieved, "claimed": claimed,
                    "perDay": round(signups / days, 2), "obRate": pct(onboarded, signups), "actRate": pct(achieved, onboarded), "claimRate": pct(claimed, achieved)})
    return out


# ----------------------------------------------------------------------------------------------------------------
# Summary for the notes writer
# ----------------------------------------------------------------------------------------------------------------
def summarise(data, top24h, cfg, today):
    P, S = data["PACE"], data["SNAPSHOT"]
    refs = data["REFERRERS_RAW"]
    acts = lambda r: r[7]
    full = S["fullDays"]
    shares = [m["firstN"] / m["full"] for m in P["months"] if m["full"]] if full else []
    t = P["sepToDate"]
    proj = {"mid": round(t / (sum(shares) / len(shares))) if shares else None, "low": round(t / max(shares)) if shares else None,
            "high": round(t / min(shares)) if shares else None, "straight": round(t / full * P["daysInMonth"]) if full else None}
    left = P["daysInMonth"] - full
    need = (P["target"] - t) if P["target"] else None
    D = data["DAILY"]
    cohorts_mix = {}
    for c in ["FT", "RN", "R1", "R3"]:
        g = [r for r in refs if r[9] == c]
        sg, ob = sum(r[5] for r in g), sum(r[6] for r in g)
        cohorts_mix[c] = {"referrers": len(g), "signups": sg, "each": round(sg / len(g), 2) if g else 0, "obPct": pct(ob, sg, 0), "activations": sum(acts(r) for r in g)}
    one = [r for r in refs if r[5] == 1]
    many = [r for r in refs if r[5] > 1]
    gold = data["GOLD"]
    pre = [w for w in gold["weekly"] if not w["post"]]
    post = [w for w in gold["weekly"] if w["post"]]
    tr = data["TRENDS"]
    return {
        "asOf": S["asOf"], "today": today.isoformat(), "campaignEnded": S.get("campaignEnded", False),
        "pace": {"month": P["monthName"], "fullDays": full, "toDate": t, "todaySoFar": P["todaySoFar"], "target": P["target"], "stretchPlus": P["stretchPlus"], "daysInMonth": P["daysInMonth"],
                 "daysLeftInclToday": left, "monthShares": [{"month": m["month"], "pctByDay": round(100 * m["firstN"] / m["full"], 1) if m["full"] else None, "full": m["full"]} for m in P["months"]],
                 "projection": proj, "last7Avg": round(sum(P["sepDaily"][-7:]) / max(1, len(P["sepDaily"][-7:])), 1), "stillNeeded": need,
                 "neededPerDayInclToday": round(need / left, 1) if need is not None and left else None, "daily": P["sepDaily"]},
        "daily": {"lastDay": D[-1] if D else None, "last7": D[-7:], "bestDay": max(D, key=lambda x: x["signups"]) if D else None,
                  "campaignWeeks": [{"week": w["week"], "signups": w["signups"], "referrers": w["referrers"], "perRef": w["perRef"]} for w in data["WEEKLY"] if w["period"] == "campaign"],
                  "top24h": top24h, "flagThreshold": 25},
        "ladder": {"referrers": len(refs), "unlocked": sum(1 for r in refs if acts(r) >= 1), "claimedAny": sum(1 for r in refs if r[8]),
                   "pipelineUnderZero": sum(r[6] for r in refs if acts(r) == 0), "atLeast3": sum(1 for r in refs if acts(r) >= 3), "exactly2": sum(1 for r in refs if acts(r) == 2),
                   "exactly4": sum(1 for r in refs if acts(r) == 4), "atLeast8": [r[0] for r in refs if acts(r) >= 8],
                   "top": [{"id": r[0], "activations": acts(r), "onboarded": r[6], "signups": r[5], "claimed": r[8]} for r in sorted(refs, key=lambda r: (-acts(r), -r[6]))[:10]]},
        "cohorts": data["COHORTS"], "cohortLabels": data["COHORT_LABELS"],
        "mix": cohorts_mix,
        "weeklyQuality": data["QUALITY"], "claims": data["CLAIMS"], "popup": data["POPUP"],
        "referrers": {"total": len(refs), "signups": sum(r[5] for r in refs), "onboarded": sum(r[6] for r in refs), "activations": sum(acts(r) for r in refs),
                      "single": {"n": len(one), "obPct": pct(sum(r[6] for r in one), len(one), 0)},
                      "multi": {"n": len(many), "signups": sum(r[5] for r in many), "obPct": pct(sum(r[6] for r in many), sum(r[5] for r in many), 0), "activations": sum(acts(r) for r in many)},
                      "topBySignups": [{"id": r[0], "signups": r[5], "onboarded": r[6], "activations": acts(r)} for r in sorted(refs, key=lambda r: -r[5])[:4]],
                      "zeroOnboarded": {"n": sum(1 for r in refs if r[6] == 0), "signups": sum(r[5] for r in refs if r[6] == 0)},
                      "neverActivatedSelf": {"n": sum(1 for r in refs if not r[4]), "signups": sum(r[5] for r in refs if not r[4]), "onboarded": sum(r[6] for r in refs if not r[4]), "activations": sum(acts(r) for r in refs if not r[4])}},
        "refereeQuality": {"funnel": [{**f, "medianFirstUsd": round(f["medianFirstInr"] / data["FX"]) if f["medianFirstInr"] else None} for f in data["Q_FUNNEL"]],
                           "bt": data["Q_BT"], "vol": data["Q_VOL"], "fx": data["FX"], "refreshedOn": data.get("qualityRefreshedOn")},
        "trends": {"last4": tr[-4:], "sameMonthLastYearAvailable": len(tr) >= 13},
        "gold": {"label": gold["label"], "dayN": gold["dayN"], "pinned": gold["pinned"], "funnel": gold["funnel"], "widgetUsers": gold.get("widgetUsers"), "claims": gold["claims"],
                 "daysToFirst": gold["daysToFirst"], "lastDays": gold["daily"][-7:],
                 "preWeeks": {"n": len(pre), "avgReferrers": round(sum(w["referrers"] for w in pre) / len(pre), 1) if pre else None, "avgShareRate": round(sum((w["shareRate"] or 0) for w in pre) / len(pre), 2) if pre else None},
                 "postWeeks": post},
        "campaigns": data["CAMPAIGNS"],
    }


# ----------------------------------------------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    cfg = json.loads((ROOT / "config.json").read_text())
    data_path = ROOT / "data.json"
    old = json.loads(data_path.read_text()) if data_path.exists() else {}
    RAW.mkdir(exist_ok=True)

    if "--notes-only" in args:
        notes_path = RAW / "notes.json"
        if not notes_path.exists():
            sys.exit("raw/notes.json not found")
        notes = json.loads(notes_path.read_text())
        if not isinstance(notes, dict):
            sys.exit("raw/notes.json must be an object")
        old["notes"] = {**old.get("notes", {}), **notes}
        data_path.write_text(json.dumps(old, ensure_ascii=False, indent=1) + "\n")
        print(f"Merged {len(notes)} notes into data.json")
        return

    now = dt.datetime.now(IST)
    today = now.date()
    start, end = d(cfg["campaign_start"]), d(cfg["campaign_end"])
    src = Sources(load_creds())

    pace_rows = query(src, cfg, "02_org_pace.sql")
    camp_rows = query(src, cfg, "01_campaign.sql")
    cohort_rows = query(src, cfg, "03_cohorts.sql")
    ref_rows = query(src, cfg, "04_referrers.sql")
    trend_rows = query(src, cfg, "06_trends.sql")
    gold_rows = query(src, cfg, "07_goldcoin.sql")
    hist_rows = query(src, cfg, "08_campaigns.sql")

    data = {k: v for k, v in old.items()}  # keep every key the current file has
    data["SNAPSHOT"] = {"asOf": f"{today.day} {MONTHS[today.month - 1]} {today.year}, {now:%H:%M} IST", "asOfIso": now.isoformat(timespec="minutes"),
                        "campaignStart": cfg["campaign_start"], "campaignEnd": cfg["campaign_end"], "campaignDay": min((today - start).days + 1, (end - start).days + 1),
                        "campaignDays": (end - start).days + 1, "daysLeft": max(0, (end - today).days), "campaignEnded": today > end,
                        "fullDays": today.day - 1, "campaignFullDays": (today - start).days}
    data["PACE"] = build_pace(pace_rows, cfg, today)
    data["DAILY"], data["QUALITY"], data["WEEKLY"], data["CLAIMS"], top24h = build_campaign(camp_rows)
    data["COHORTS"] = build_cohorts(cohort_rows)
    prev_m = today.replace(day=1) - dt.timedelta(days=1)
    data["COHORT_LABELS"] = {"now": MONTHS[today.month - 1], "prev": MONTHS[prev_m.month - 1]}
    data["REFERRERS_RAW"] = json.loads(ref_rows[0][4]) if ref_rows and ref_rows[0][4] else []
    data["TRENDS"] = build_trends(trend_rows, today)
    data["GOLD"] = build_gold(gold_rows, cfg, today, src)
    data["CAMPAIGNS"] = build_campaigns(hist_rows, cfg, today)

    if "--force-quality" in args or old.get("qualityRefreshedOn") != today.isoformat() or not all(k in old for k in ("Q_FUNNEL", "Q_BT", "Q_VOL", "FX")):
        data["Q_FUNNEL"], data["Q_BT"], data["Q_VOL"], data["FX"] = build_quality(query(src, cfg, "05_referee_quality.sql"), today)
        data["qualityRefreshedOn"] = today.isoformat()

    yesterday = today - dt.timedelta(days=1)
    try:
        wt = cfg.get("milestone_widget_type", "moonshot_campaign")
        data["POPUP"] = {"widgetUniqueUsers": src.mixpanel_unique("referral_widget_loaded", f'properties["type"] == "{wt}"', start, yesterday),
                         "claimCta": src.mixpanel_unique("referral_milestone_claim_cta_click", 'properties["type"] != ""', start, yesterday),
                         "claimConfirm": src.mixpanel_unique("referral_milestone_claim_confirm_click", 'properties["type"] != ""', start, yesterday),
                         "keepReferring": src.mixpanel_unique("referral_milestone_keep_referring_click", "1 == 1", start, yesterday),
                         "window": f"{lbl(start.isoformat())} to {lbl(yesterday.isoformat())}", "stale": False}
    except Exception as e:  # noqa: BLE001
        data["POPUP"] = {**old.get("POPUP", {}), "stale": True, "error": str(e)[:200]}

    data.setdefault("notes", {})
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    summary = summarise(data, top24h, cfg, today)
    (RAW / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    g = data["GOLD"]["funnel"]
    print(f"OK {data['SNAPSHOT']['asOf']}: {data['PACE']['monthName']} onboardings {data['PACE']['sepToDate']} + {data['PACE']['todaySoFar']} today; "
          f"{len(data['REFERRERS_RAW'])} campaign referrers; gold coin {g['signups']} signups / {g['achieved']} activated / {g['claimed']} claimed; "
          f"popup {'stale' if data['POPUP'].get('stale') else 'fresh'}; quality refreshed {data.get('qualityRefreshedOn')}")
    if top24h and top24h[0]["signups"] > 25:
        print(f"CHECK: referrer {top24h[0]['id']} has {top24h[0]['signups']} signups in the last 24 hours")


if __name__ == "__main__":
    main()
