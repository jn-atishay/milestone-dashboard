# Skydo referrals dashboard

A static page (`index.html`) that renders everything from `data.json`. An hourly job on a Mac rebuilds `data.json` from Metabase and Mixpanel and pushes it; GitHub Pages serves the latest commit.

Tabs: Overview (program-wide trends), Milestone campaign (the Sep to Oct 2026 ladder), Gold coin (the never-referrer campaign pinned on 16 Oct 2026), Referrers (every milestone referrer), Referee quality, Campaigns (every gift campaign since 2025 side by side).

## Files
- `index.html` built page. Rebuild after editing `src/dashboard.jsx` with `python3 scripts/build_html.py`.
- `data.json` the only file the refresh job changes.
- `config.json` campaign ids and dates, monthly targets, excluded and flagged referrers, the gold coin campaign, the campaign history list, whether customer names are shown.
- `queries/` the SQL the refresh runs. Placeholders (`{{EXCLUDED}}`, `{{ALWAYS_EXCLUDED}}`, `{{CAMPAIGN_ID}}`, `{{GOLD_CAMPAIGN_ID}}`, ...) are filled from `config.json`.
- `scripts/refresh.py` runs every query plus the Mixpanel counts and rebuilds `data.json` (about 20 seconds). `--notes-only` merges `raw/notes.json` into `data.json` without querying.
- `scripts/validate.py` blocks a commit if data is malformed or contains customer emails, phone numbers or unwanted names.
- `ROUTINE.md` the prompt for the scheduled job: run the script, write the notes, validate, push.
- `raw/` (ignored by git) the script's `summary.json` for the notes writer and the job's `notes.json`.

## How a refresh works
1. `python3 scripts/refresh.py` pulls the numbers. Credentials come from environment variables (`METABASE_URL`, `METABASE_API_KEY`, `MIXPANEL_USER`, `MIXPANEL_SECRET`, `MIXPANEL_PROJECT`) or, failing that, from the Metabase and Mixpanel MCP entries in the Claude Desktop config on the same machine. Nothing is stored in this repository.
2. The scheduled Claude job writes `raw/notes.json` from `raw/summary.json`, merges it with `--notes-only`, runs the validator, commits `data.json` and pushes.
3. GitHub Pages rebuilds within a minute. The page shows "Updated ... ago" in the top bar and turns amber after three hours without a refresh.

## One-time setup
1. Create a repository, add these files and push. Settings > Pages > Deploy from branch > main, folder `/ (root)`.
2. Install the Metabase and Mixpanel MCP servers in Claude Desktop on the machine that will run the job, or export the five environment variables.
3. Schedule `claude -p "$(cat ROUTINE.md)"` hourly from the repository folder (the launchd job on the current machine logs to `logs/refresh.log`). Run it once by hand and check the result before trusting the schedule.

## Privacy
GitHub Pages sites are public unless the organisation has GitHub Enterprise Cloud with private Pages. Anyone with the link can see campaign metrics, targets, exporter ids and, when `show_customer_names` is true, referrer names. The validator refuses emails and phone numbers.

## Adding or removing a flagged referrer
Edit `flagged_referrers` in `config.json`. The next run excludes them from campaign metrics; their onboardings still count toward the monthly target. `always_excluded_referrers` removes a referrer from every number on the page, the target included.
