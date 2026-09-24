-- Campaign-level daily funnel, weekly quality, weekly referrals, claims.
-- {{EXCLUDED}} = always_excluded_referrers + flagged_referrers from config.json, comma separated.
-- Output columns: g, k, k2, v1..v6 (all text). One row group per dashboard block.
WITH today AS (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date AS d),
rel AS (
  SELECT rr.id, rr.referrer_exporter_id, rr.referral_state, rr.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS sat
  FROM referral_relation rr
  WHERE rr.campaign_id = {{CAMPAIGN_ID}} AND rr.is_deleted = false
    AND rr.referrer_exporter_id IS NOT NULL AND rr.referrer_exporter_id NOT IN ({{EXCLUDED}})
),
tr AS (
  SELECT referral_relation_id,
    MIN(action_timestamp) FILTER (WHERE referral_state = 'ONBOARDING_COMPLETE') AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS ob,
    MIN(action_timestamp) FILTER (WHERE referral_state = 'ACHIEVED') AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS act
  FROM referral_milestone_tracking WHERE is_deleted = false GROUP BY 1
),
j AS (SELECT r.*, tr.ob, tr.act FROM rel r LEFT JOIN tr ON tr.referral_relation_id = r.id),
days AS (SELECT g::date AS d FROM today, generate_series(DATE '{{CAMPAIGN_START}}', today.d - 1, INTERVAL '1 day') g)
SELECT 'daily' AS g, days.d::text AS k, TO_CHAR(days.d, 'Dy') AS k2,
  (SELECT COUNT(*) FROM j WHERE j.sat::date = days.d)::text AS v1,
  (SELECT COUNT(DISTINCT referrer_exporter_id) FROM j WHERE j.sat::date = days.d)::text AS v2,
  (SELECT COUNT(*) FROM j WHERE j.ob::date = days.d)::text AS v3,
  (SELECT COUNT(*) FROM j WHERE j.act::date = days.d)::text AS v4,
  (SELECT COUNT(*) FROM referral_milestone_claim c WHERE c.campaign_id = {{CAMPAIGN_ID}} AND c.is_deleted = false AND c.status = 'CLAIMED'
     AND c.referrer_exporter_id NOT IN ({{EXCLUDED}})
     AND (c.claimed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date = days.d)::text AS v5,
  NULL AS v6
FROM days
UNION ALL
SELECT 'quality', date_trunc('week', sat)::date::text, NULL, COUNT(*)::text,
  ROUND(100.0 * COUNT(*) FILTER (WHERE ob <= sat + interval '1 day') / COUNT(*), 1)::text,
  ROUND(100.0 * COUNT(*) FILTER (WHERE ob <= sat + interval '7 days') / COUNT(*), 1)::text,
  ROUND(100.0 * COUNT(ob) / COUNT(*), 1)::text,
  ROUND(100.0 * COUNT(act) / NULLIF(COUNT(ob), 0), 1)::text,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM (act - ob)) / 86400)::numeric, 1)::text
FROM j GROUP BY 2
UNION ALL
SELECT 'weekly', date_trunc('week', rr.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date::text,
  CASE WHEN rr.referral_date >= DATE '{{CAMPAIGN_START}}' - 1 THEN 'campaign' ELSE 'pre' END,
  COUNT(*)::text, COUNT(DISTINCT rr.referrer_exporter_id)::text,
  ROUND(COUNT(*)::numeric / COUNT(DISTINCT rr.referrer_exporter_id), 2)::text, NULL, NULL, NULL
FROM referral_relation rr
WHERE rr.is_deleted = false AND rr.referral_date >= DATE '{{CAMPAIGN_START}}' - 57
  AND rr.referrer_exporter_id IS NOT NULL AND rr.referrer_exporter_id NOT IN ({{EXCLUDED}})
  AND rr.referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED')
GROUP BY 2, 3
UNION ALL
SELECT 'claims', m.label, c.status, m.threshold::text, COUNT(*)::text,
  MIN(c.claimed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date::text,
  MAX(c.claimed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date::text,
  ROUND(AVG(c.achieved_count), 1)::text, NULL
FROM referral_milestone_claim c JOIN referral_campaign_milestone m ON m.id = c.milestone_id
WHERE c.campaign_id = {{CAMPAIGN_ID}} AND c.is_deleted = false AND c.referrer_exporter_id NOT IN ({{EXCLUDED}})
GROUP BY 2, 3, 4
ORDER BY 1, 2;
