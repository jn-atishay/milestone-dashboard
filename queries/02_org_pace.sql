-- All referral onboardings (every campaign, referee deduped to earliest referrer), the definition the monthly target uses.
-- Flagged referrers are NOT excluded here: their onboardings are real onboardings.
-- Rows: 'month' = previous three months (full month, and first N days where N = full days elapsed this month);
--       'day'   = each full day of the current month.
WITH today AS (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date AS d),
n AS (SELECT EXTRACT(day FROM d)::int - 1 AS full_days, date_trunc('month', d)::date AS m0 FROM today),
referee_ob AS (SELECT exporter_id, MIN(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS fo FROM cc_account GROUP BY 1),
rd AS (
  SELECT DISTINCT ON (referee_exporter_id) referee_exporter_id FROM referral_relation
  WHERE referral_state IN ('ONBOARDING_COMPLETE','ACHIEVED') AND is_deleted = false
    AND referrer_exporter_id IS NOT NULL AND referrer_exporter_id NOT IN (2,3,4,14,38679)
  ORDER BY referee_exporter_id, referral_date
),
org AS (SELECT ro.fo AS ts FROM rd JOIN referee_ob ro ON ro.exporter_id = rd.referee_exporter_id, n WHERE ro.fo >= n.m0 - INTERVAL '3 months')
SELECT 'month' AS g, TO_CHAR(date_trunc('month', ts), 'YYYY-MM') AS k, COUNT(*) AS full_month,
       COUNT(*) FILTER (WHERE EXTRACT(day FROM ts) <= (SELECT full_days FROM n)) AS first_n
FROM org, n WHERE ts < n.m0 GROUP BY 2
UNION ALL
SELECT 'day', ts::date::text, COUNT(*), NULL
FROM org, n, today WHERE ts >= n.m0 AND ts::date < today.d GROUP BY 2
ORDER BY 1, 2;
