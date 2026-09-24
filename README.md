# Milestone referral campaign dashboard

A static page (`index.html`) that renders everything from `data.json`. A scheduled Claude job rebuilds `data.json` every hour from Metabase and Mixpanel and pushes it; GitHub Pages serves the latest commit.

## Files
- `index.html` built page. Rebuild after editing `src/dashboard.jsx` with `python scripts/build_html.py`.
- `data.json` the only file the refresh job changes.
- `config.json` campaign dates, monthly targets, excluded and flagged referrers, whether customer names are shown.
- `queries/` the SQL the job runs.
- `scripts/validate.py` blocks a commit if data is malformed or contains customer emails, phone numbers or unwanted names.
- `ROUTINE.md` the prompt for the scheduled job.

## One-time setup
1. Create a repository (private is fine), add these files and push.
2. Settings > Pages > Deploy from branch > main, folder `/ (root)`. The link appears there after a minute.
3. Set up the hourly job (see below) with `ROUTINE.md` as the prompt. Click Run now once and check the result before turning the schedule on.

## Where the job can run
The Metabase connector in this workspace runs through the Claude Desktop app on your machine, so a cloud routine cannot see it.
- **Desktop scheduled task (simplest):** runs on your laptop with the same Metabase access you have in chat. It only runs while the laptop is awake and the app is open.
- **Cloud routine (runs 24x7):** needs a Metabase API key stored as a secret in the routine's environment, and the prompt changed to call Metabase's REST API instead of the connector. Ask your Metabase admin for a read-only key scoped to this database. Mixpanel can use the cloud Mixpanel connector.

Hourly runs count against your Claude usage and your plan's daily routine cap. 9 AM to 9 PM IST (13 runs) covers the working day at half the cost.

## Privacy
GitHub Pages sites are public unless your organization has GitHub Enterprise Cloud with private Pages. Anyone with the link can see campaign metrics, targets and exporter IDs. Customer names are off (`show_customer_names: false`) and the validator refuses emails and phone numbers. Keep it that way unless the site is access-controlled.

## Adding or removing a flagged referrer
Edit `flagged_referrers` in `config.json`. The next run excludes them from campaign metrics and writes the excluded note. Their onboardings still count toward the monthly target.
