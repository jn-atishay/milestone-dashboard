-- One row per campaign referrer, returned as a single JSON array in column j.
-- Row: [exporter_id, name, business_type_code, own_onboarding_date, own_activation_date, signups, onboardings, activations, gift_code, cohort_code]
-- name is returned blank unless {{SHOW_NAMES}} is true. Never add emails or phone numbers.
WITH rel AS (
  SELECT rr.referrer_exporter_id, rr.referral_state FROM referral_relation rr
  WHERE rr.campaign_id = {{CAMPAIGN_ID}} AND rr.is_deleted = false AND rr.referrer_exporter_id IS NOT NULL
    AND rr.referrer_exporter_id NOT IN ({{EXCLUDED}})
),
per_ref AS (
  SELECT referrer_exporter_id AS id, COUNT(*) s,
    COUNT(*) FILTER (WHERE referral_state IN ('ONBOARDING_COMPLETE','ACHIEVED')) o,
    COUNT(*) FILTER (WHERE referral_state = 'ACHIEVED') a
  FROM rel GROUP BY 1
),
prior AS (
  SELECT referrer_exporter_id AS id, COUNT(*) ps, COUNT(*) FILTER (WHERE referral_state = 'ACHIEVED') pa FROM referral_relation
  WHERE is_deleted = false AND referral_date < DATE '{{CAMPAIGN_START}}' AND referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED') GROUP BY 1
),
claimed AS (
  SELECT referrer_exporter_id AS id, string_agg(m.label, ', ') cl FROM referral_milestone_claim c
  JOIN referral_campaign_milestone m ON m.id = c.milestone_id
  WHERE c.campaign_id = {{CAMPAIGN_ID}} AND c.is_deleted = false AND c.status = 'CLAIMED' GROUP BY 1
),
ob AS (SELECT exporter_id AS id, MIN(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date d FROM cc_account GROUP BY 1),
act AS (SELECT exporter_id AS id, MIN(settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date d FROM public."transaction" WHERE transaction_state = 'EXPORTER_SUCCESS' GROUP BY 1),
bt AS (
  SELECT id, CASE business_type::text WHEN 'FREELANCER' THEN 'F' WHEN 'SOLE_PROPRIETORSHIP' THEN 'SP' WHEN 'COMPANY' THEN 'C'
    WHEN 'LIMITED_LIABILITY_PARTNERSHIP' THEN 'LLP' WHEN 'PARTNERSHIP' THEN 'PT' WHEN 'HINDU_UNDIVIDED_FAMILY' THEN 'HUF' ELSE '' END AS b
  FROM exporter
),
rows_ AS (
  SELECT p.id,
    CASE WHEN {{SHOW_NAMES}} THEN COALESCE(initcap((SELECT MIN(full_name) FROM exporter_user u WHERE u.exporter_id = p.id)), '') ELSE '' END AS name,
    bt.b, ob.d::text AS obd, act.d::text AS actd, p.s, p.o, p.a,
    CASE WHEN c.cl IS NULL THEN '' WHEN c.cl ILIKE '%polaroid%' THEN 'P' ELSE c.cl END AS gift,
    CASE WHEN COALESCE(pr.ps, 0) = 0 THEN 'FT' WHEN COALESCE(pr.pa, 0) = 0 THEN 'RN' WHEN pr.pa <= 2 THEN 'R1' ELSE 'R3' END AS cohort
  FROM per_ref p LEFT JOIN prior pr USING (id) LEFT JOIN claimed c USING (id) LEFT JOIN ob USING (id) LEFT JOIN act USING (id) LEFT JOIN bt USING (id)
)
SELECT COUNT(*) AS n, SUM(s) AS signups, SUM(o) AS onboardings, SUM(a) AS activations,
  json_agg(json_build_array(id, name, b, obd, actd, s, o, a, gift, cohort) ORDER BY a DESC, o DESC, s DESC, id)::text AS j
FROM rows_;
