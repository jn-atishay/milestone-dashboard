# Hourly refresh: routine prompt

This whole file is the prompt for the scheduled job (launchd runs `claude -p "$(cat ROUTINE.md)"` in this repository every hour).

---

You refresh the Skydo referrals dashboard in this repository. The page (`index.html`) renders entirely from `data.json`. A script rebuilds the numbers; your job is to write the plain-language notes, check the result, and push it. Do not edit `index.html`, `src/`, `queries/`, `scripts/` or `config.json`.

## 1. Rebuild the numbers
- Run `TZ=Asia/Kolkata date` to know the current time. Do not trust any date injected into your context.
- Run `python3 scripts/refresh.py`. It queries Metabase and Mixpanel, rebuilds every data block in `data.json` (keeping the current notes), and writes `raw/summary.json` with the figures you need for the notes. It prints one `OK ...` line on success.
- If it exits non-zero, run it once more. If it still fails, stop here, do not commit, and report the error it printed. The page keeps showing the last good data.
- If it prints a `CHECK:` line, a referrer sent more than 25 campaign signups in the last 24 hours. Do not change `config.json`. Mention the exporter id and count in `notes.daily` and in your run summary so a person can decide.

## 2. Write the notes
Read `raw/summary.json` (every number you need is there; `data.json` has the full blocks if you want more). Then write `raw/notes.json`: a JSON object with every key below. Each note is a short plain-language read of the numbers next to it, for a founder audience. Rewrite each one from this run's data, keeping the same job:

- `pace`: projection, straight line, week by week, what the target needs per day for the rest of the month. If `pace.target` is null, say no target is set for the month and give the projection only.
- `daily`: week-by-week campaign signups and anything unusual in the last full day. Name any referrer from `daily.top24h` above 25 signups.
- `ladder`: pipeline waiting to activate, anyone who crossed a rung, how many are one activation from the next rung.
- `cohorts`: the overall lift and which cohorts carry it; always say what is happening to never-referrers (1a).
- `mix`, `weeklyQuality`, `claims`, `popupHeader`, `popup` (list of two), `referrers` (list of about six), `refereeQuality` (list of about five), `qualityHeader`, `qualityWindow`.
- `overview` (list of three): the program-level read from `trends`: how this month compares with the last few on signups, onboardings and activations, where share rate and the referral share of all onboardings are heading, and the one thing worth attention. Say clearly when the current month is partial.
- `gold` (list of three): the gold coin campaign from `gold`: how many of the pinned never-referrers have acted, the before-and-after weekly share rate of the group, how fast first referrals came after the pin, what is activating and being claimed. Be honest about small numbers.
- `campaigns` (list of two): how the live campaigns compare with past gift campaigns on signups per day, onboarding and activation rates, and gifts claimed, using `campaigns`.
- `excluded`: keep the current text (read it from `data.json`) unless `flagged_referrers` in `config.json` changed. If a new referrer is flagged, write one factual paragraph on what they did.

If `popup.stale` is true, say in `popupHeader` that Mixpanel did not answer on this run and the popup numbers are from the previous one.

Rules: plain words, no em dashes, no emojis, no names, emails or phone numbers of customers (refer to them as "exporter 12345"). Only state numbers you read from this run's summary or data. If nothing changed since the last notes, say so briefly rather than inventing a story.

## 3. Merge, check and publish
- Run `python3 scripts/refresh.py --notes-only` to merge `raw/notes.json` into `data.json`.
- Run `python3 scripts/validate.py`. If it fails, fix `raw/notes.json`, merge again and rerun. If it still fails, do not commit; report the errors.
- Commit only `data.json` with the message `data: refresh <asOf>` (asOf from `raw/summary.json`) and push to the default branch.
- End with a two-line summary: the headline numbers (month onboardings against target, campaign signups and activations, gold coin referrers and coins) and anything a person should look at.
