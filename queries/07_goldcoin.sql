-- Gold coin campaign ({{GOLD_CAMPAIGN_ID}}): never-referrers pinned to the campaign get a gold coin for their first activated referral.
-- Rows: g = day | funnel | pinned | claims | days_to_first | week. Columns g, k, v1..v6 (text).
WITH today AS (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date d),
p AS (SELECT exporter_id, updated_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' pinned_at FROM user_referral_data WHERE pinned_campaign_id = {{GOLD_CAMPAIGN_ID}} AND is_deleted = false),
rr AS (
  SELECT r.referrer_exporter_id ref, r.referee_exporter_id referee, r.referral_state::text st, r.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' sat
  FROM referral_relation r
  WHERE r.campaign_id = {{GOLD_CAMPAIGN_ID}} AND r.is_deleted = false AND r.referrer_exporter_id IS NOT NULL
    AND r.referrer_exporter_id NOT IN ({{EXCLUDED}}) AND r.referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED')
),
prr AS (
  SELECT r.referrer_exporter_id ref, r.referee_exporter_id referee, r.referral_state::text st, (r.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date sd
  FROM referral_relation r JOIN p ON p.exporter_id = r.referrer_exporter_id
  WHERE r.is_deleted = false AND r.referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED')
),
days AS (SELECT g::date d FROM today, generate_series(DATE '{{GOLD_START}}', today.d, INTERVAL '1 day') g),
wk AS (SELECT (DATE '{{GOLD_START}}' + (i * 7))::date ws FROM generate_series(-9, 12) i, today WHERE DATE '{{GOLD_START}}' + (i * 7) <= today.d)
SELECT 'day' g, d::text k, (SELECT COUNT(*) FROM rr WHERE sat::date = d)::text v1, (SELECT COUNT(DISTINCT ref) FROM rr WHERE sat::date = d)::text v2,
  (SELECT COUNT(*) FROM rr WHERE sat::date = d AND st IN ('ONBOARDING_COMPLETE','ACHIEVED'))::text v3, (SELECT COUNT(*) FROM rr WHERE sat::date = d AND st = 'ACHIEVED')::text v4, NULL v5, NULL v6
FROM days
UNION ALL
SELECT 'funnel', 'all', COUNT(*)::text, COUNT(DISTINCT ref)::text, COUNT(*) FILTER (WHERE st IN ('ONBOARDING_COMPLETE','ACHIEVED'))::text, COUNT(*) FILTER (WHERE st = 'ACHIEVED')::text,
  (SELECT COUNT(*) FROM referral_milestone_claim k WHERE k.campaign_id = {{GOLD_CAMPAIGN_ID}} AND k.is_deleted = false AND k.status = 'CLAIMED')::text,
  (SELECT COUNT(*) FROM (SELECT DISTINCT ref FROM rr) f WHERE NOT EXISTS (SELECT 1 FROM referral_relation x WHERE x.referrer_exporter_id = f.ref AND x.is_deleted = false
     AND x.referral_date < DATE '{{GOLD_START}}' AND x.referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED')))::text
FROM rr
UNION ALL
SELECT 'pinned', 'all', COUNT(*)::text, MIN(pinned_at)::date::text,
  (SELECT COUNT(*) FROM p WHERE EXISTS (SELECT 1 FROM public."transaction" t WHERE t.exporter_id = p.exporter_id AND t.transaction_state = 'EXPORTER_SUCCESS' AND t.settlement_date >= now() - INTERVAL '90 days'))::text,
  (SELECT COUNT(DISTINCT ref) FROM prr WHERE sd < DATE '{{GOLD_START}}')::text, NULL, NULL
FROM p
UNION ALL
SELECT 'claims', (k.claimed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date::text, k.referrer_exporter_id::text, k.status, COALESCE(k.claim_source, ''), NULL, NULL, NULL
FROM referral_milestone_claim k WHERE k.campaign_id = {{GOLD_CAMPAIGN_ID}} AND k.is_deleted = false
UNION ALL
SELECT 'days_to_first', FLOOR(EXTRACT(epoch FROM (f.first_sat - p.pinned_at)) / 86400)::int::text, COUNT(*)::text, NULL, NULL, NULL, NULL, NULL
FROM (SELECT ref, MIN(sat) first_sat FROM rr GROUP BY 1) f JOIN p ON p.exporter_id = f.ref GROUP BY 2
UNION ALL
SELECT 'week', wk.ws::text, COUNT(DISTINCT prr.ref)::text, COUNT(prr.referee)::text,
  COUNT(prr.referee) FILTER (WHERE st IN ('ONBOARDING_COMPLETE','ACHIEVED'))::text, COUNT(prr.referee) FILTER (WHERE st = 'ACHIEVED')::text,
  (SELECT COUNT(DISTINCT t.exporter_id) FROM public."transaction" t JOIN p ON p.exporter_id = t.exporter_id
     WHERE t.transaction_state = 'EXPORTER_SUCCESS' AND (t.settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date >= wk.ws
       AND (t.settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date < wk.ws + 7)::text, NULL
FROM wk LEFT JOIN prr ON prr.sd >= wk.ws AND prr.sd < wk.ws + 7
GROUP BY wk.ws
ORDER BY 1, 2;
