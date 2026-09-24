# Hourly refresh: routine prompt

Paste everything below the line into the routine (or Desktop scheduled task) as its prompt.
It assumes the routine has this repository checked out and has access to the Metabase and Mixpanel connectors.

---

You refresh the milestone referral campaign dashboard in this repository. The page (`index.html`) renders entirely from `data.json`. Your job is to rebuild `data.json` from live data, check it, and push it. Do not edit `index.html`, `src/`, `queries/` or `config.json`.

## 0. Before you start
- Read `config.json`. Build EXCLUDED as the comma-separated union of `always_excluded_referrers` and `flagged_referrers`.
- Work out today's date and time in IST with `TZ=Asia/Kolkata date`. Do not trust any date injected into your context.
- If today is after `campaign_end` plus one day, stop without changing anything and say the campaign has ended.
- Read the current `data.json` so you can keep anything you are told to keep.

## 1. Run the queries (Metabase database `metabase_database_id`)
For each file in `queries/`, replace `{{EXCLUDED}}`, `{{CAMPAIGN_ID}}`, `{{CAMPAIGN_START}}` from config and `{{SHOW_NAMES}}` with `true` or `false` from `show_customer_names`. Strip comment lines. Run it with the Metabase execute-query tool.
- Every run: `01_campaign.sql`, `02_org_pace.sql`, `03_cohorts.sql`, `04_referrers.sql`.
- Once a day only: `05_referee_quality.sql`. Run it if `data.json` has no `qualityRefreshedOn` or it is not today; otherwise keep `Q_FUNNEL`, `Q_BT`, `Q_VOL`, `FX` and `qualityRefreshedOn` as they are.
- If a query errors or times out, retry once. If it still fails, stop, do not commit, and report which query failed. The page keeps showing the last good data.

## 2. Run the Mixpanel queries (segmentation, unique users, from the campaign start to yesterday)
- `referral_widget_loaded`, where `properties["type"] == "moonshot_campaign"` -> `POPUP.widgetUniqueUsers`
- `referral_milestone_claim_cta_click`, where `properties["type"] != ""` -> `POPUP.claimCta`
- `referral_milestone_claim_confirm_click`, where `properties["type"] != ""` -> `POPUP.claimConfirm`
- `referral_milestone_keep_referring_click`, where `1 == 1` -> `POPUP.keepReferring`
- `POPUP.window` = "1 to 23 Sep" style text for that date range.
If Mixpanel fails, keep the previous `POPUP` block and say so in `notes.popupHeader`.

## 3. Build data.json
Dates on the page are written like "24 Sep". Keep every key the current file has. Mapping:

- `SNAPSHOT`: `asOf` "24 Sep 2026, 14:00 IST"; `campaignDay` = days since campaign_start + 1; `daysLeft` = campaign_end minus today; `fullDays` = full days elapsed in the current month (day of month minus 1); `campaignFullDays` = days since campaign_start.
- `PACE` (from 02): `months` = the three `month` rows, oldest first, as `{month: "Jun", firstN, full}`; `sepDaily` = the `day` rows as a list of counts from day 1 to yesterday, with 0 for missing days; `sepToDate` = sum of `sepDaily`; `todaySoFar` = the count on the `today` row (onboardings so far today, 0 if none); `target` and `stretchPlus` from `config.targets["YYYY-MM"]`; `monthName` ("September"), `monthShort` ("Sep"), `daysInMonth`. The keys are called `sep...` for every month; keep the names.
- `DAILY` (01, g = daily): `{day: "1 Sep", dow: k2, signups: v1, referrers: v2, onboardings: v3, activations: v4, claims: v5}` as numbers.
- `QUALITY` (01, g = quality): `{week: "7 Sep", signups: v1, ob1d: v2, ob7d: v3, obSoFar: v4, actOfOb: v5, medianDays: v6}` as numbers, 0 for null.
- `WEEKLY` (01, g = weekly): `{week: "7 Sep", period: k2, signups: v1, referrers: v2, perRef: v3}`.
- `CLAIMS` (01, g = claims): `{reward: k, threshold: v1, status: "Claimed" or "Forfeited", count: v2, first: "1 Sep", last: "23 Sep", avgAchieved: v5}`.
- `COHORTS` (03): nine rows in this order with these labels and indent: 1 "Activated before month start" (0), 1a "never referred before" (1), 1b "referred in the past" (1), 1.1 "transacted this month" (1), 1.2 "recently dormant (txn in prev 3 mo)" (1), 1.3 "dormant (no txn 3+ mo)" (1), 2 "New activations this month (M0)" (0), 3 "Not activated, onboarded this month" (0), 4 "Not activated, old onboarder" (0). Fields `id, label, indent, base, refNow, rateNow, refPrev, ratePrev, delta` where `delta` = (rateNow minus ratePrev) / ratePrev x 100, one decimal.
- `COHORT_LABELS`: `{now: "Sep", prev: "Aug"}` for the current and previous month.
- `REFERRERS_RAW` (04): the parsed JSON array in column `j`, unchanged.
- `Q_FUNNEL`, `Q_BT`, `Q_VOL`, `FX` (05, daily only). Funnel rows `{src, n: v1, ob1d: v2, ob7d: v3, matureN: v4, act10: v5, medianFirstInr: v6}` with src "Aug referrals", "Sept, single-signup referrers", "Sept, 2+ signup referrers" (use the actual month names). BT rows per business type in the order Freelancer, Sole prop, Company, LLP, Partnership, HUF: `{bt, preN, preShare, preAct, cN, cShare, cAct}` from the `prev:` and `now:` rows; null where there is no row or no mature referees. Volume rows in the order Not stated, Under $10K a month, $10K to 20K, $20K to 50K, $50K and above (codes 0 to 4). `FX` = the fx value rounded to a whole number. Set `qualityRefreshedOn` to today.

## 4. Rewrite the notes
Every key in `notes` is a short plain-language read of the numbers next to it, for a founder audience. Rewrite each one from the new data, keeping the same job:
- `pace`: projection, straight line, week by week, what the target needs per day for the rest of the month.
- `daily`: week-by-week signups and anything unusual in the last day.
- `ladder`: pipeline waiting to activate, anyone who crossed a rung, how many are one activation from the next.
- `cohorts`: the overall lift and which cohorts carry it; always say what is happening to never-referrers (1a).
- `mix`, `weeklyQuality`, `claims`, `popupHeader`, `popup` (list of two), `referrers` (list of about six), `refereeQuality` (list, only on the daily run), `qualityHeader`, `qualityWindow`.
- `excluded`: keep as is unless `flagged_referrers` changed. If a new referrer is flagged, write one factual paragraph on what they did.
Rules: plain words, no em dashes, no emojis, no names, emails or phone numbers of customers (refer to them as "exporter 12345"). Only state numbers you computed from this run's data. If nothing changed, say so briefly rather than inventing a story.

### Flag unusual referrers
If any referrer not already flagged has more than 25 campaign signups in the last 24 hours, do not add them to `flagged_referrers` yourself. Mention them in `notes.daily` and in your run summary so a person can decide.

## 5. Check and publish
- Run `python scripts/validate.py`. If it fails, fix what you built and run it again. If it still fails, do not commit; report the errors.
- Commit only `data.json` with the message `data: refresh <asOf>` and push to the default branch.
- End with a two-line summary: the headline numbers and anything a person should look at.
