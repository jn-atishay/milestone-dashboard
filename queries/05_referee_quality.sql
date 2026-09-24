-- Referee quality tab: current campaign month vs the previous month. Run once a day, not every hour.
-- period2 splits current-month referees by whether their referrer sent 1 or 2+ signups this month.
WITH today AS (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date AS d),
m AS (SELECT date_trunc('month', d)::date AS m0 FROM today),
sig AS (
  SELECT DISTINCT ON (referee_exporter_id) referee_exporter_id AS id, referrer_exporter_id AS ref,
         referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS sat
  FROM referral_relation, m, today
  WHERE is_deleted = false AND referrer_exporter_id IS NOT NULL AND referrer_exporter_id NOT IN ({{EXCLUDED}})
    AND referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED')
    AND referral_date >= m.m0 - INTERVAL '1 month' AND (referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date < today.d
  ORDER BY referee_exporter_id, referral_date
),
ob AS (SELECT exporter_id AS id, MIN(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS ob_at FROM cc_account GROUP BY 1),
act AS (SELECT exporter_id AS id, MIN(settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS act_at FROM public."transaction" WHERE transaction_state = 'EXPORTER_SUCCESS' GROUP BY 1),
firsttx AS (SELECT DISTINCT ON (exporter_id) exporter_id AS id, amount_converted FROM public."transaction"
  WHERE transaction_state = 'EXPORTER_SUCCESS' AND settlement_date IS NOT NULL ORDER BY exporter_id, settlement_date),
refvol AS (SELECT ref, COUNT(*) n FROM sig, m WHERE sat >= m.m0 GROUP BY 1),
j AS (
  SELECT s.id, s.sat,
    CASE WHEN s.sat >= m.m0 THEN 'now' ELSE 'prev' END AS period,
    CASE WHEN s.sat >= m.m0 AND rv.n >= 2 THEN 'now_multi' WHEN s.sat >= m.m0 THEN 'now_single' ELSE 'prev' END AS period2,
    COALESCE(e.business_type::text, 'UNKNOWN') AS bt,
    CASE WHEN d.monthly_revenue IN ('0_10K_USD','UNDER_10L_INR') THEN '1' WHEN d.monthly_revenue = '10_20K_USD' THEN '2'
         WHEN d.monthly_revenue = '20_50K_USD' THEN '3' WHEN d.monthly_revenue IN ('50_100K_USD','>100K_USD','OVER_10L_INR') THEN '4' ELSE '0' END AS vol,
    ob.ob_at, act.act_at, ft.amount_converted,
    (ob.ob_at <= now() AT TIME ZONE 'Asia/Kolkata' - interval '10 days') AS mature10,
    (act.act_at <= ob.ob_at + interval '10 days') AS act10
  FROM sig s CROSS JOIN m LEFT JOIN exporter e ON e.id = s.id
  LEFT JOIN exporter_business_description d ON d.exporter_id = s.id AND d.is_deleted = false
  LEFT JOIN ob ON ob.id = s.id LEFT JOIN act ON act.id = s.id LEFT JOIN firsttx ft ON ft.id = s.id LEFT JOIN refvol rv ON rv.ref = s.ref
)
SELECT 'funnel' g, period2 k, COUNT(*)::text v1,
  ROUND(100.0 * COUNT(*) FILTER (WHERE ob_at <= sat + interval '1 day') / COUNT(*), 1)::text v2,
  ROUND(100.0 * COUNT(*) FILTER (WHERE ob_at <= sat + interval '7 days') / COUNT(*), 1)::text v3,
  COUNT(*) FILTER (WHERE mature10)::text v4,
  ROUND(100.0 * COUNT(*) FILTER (WHERE mature10 AND act10) / NULLIF(COUNT(*) FILTER (WHERE mature10), 0), 1)::text v5,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount_converted)::numeric)::text v6
FROM j GROUP BY 2
UNION ALL
SELECT 'bt', period || ':' || bt, COUNT(*)::text, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY period), 1)::text,
  COUNT(*) FILTER (WHERE mature10)::text,
  ROUND(100.0 * COUNT(*) FILTER (WHERE mature10 AND act10) / NULLIF(COUNT(*) FILTER (WHERE mature10), 0), 1)::text, NULL, NULL
FROM j WHERE ob_at IS NOT NULL GROUP BY period, bt
UNION ALL
SELECT 'vol', period || ':' || vol, COUNT(*)::text, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY period), 1)::text,
  COUNT(*) FILTER (WHERE mature10)::text,
  ROUND(100.0 * COUNT(*) FILTER (WHERE mature10 AND act10) / NULLIF(COUNT(*) FILTER (WHERE mature10), 0), 1)::text, NULL, NULL
FROM j WHERE ob_at IS NOT NULL GROUP BY period, vol
UNION ALL
SELECT 'fx', 'usd_inr', ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount_converted / NULLIF(amount, 0))::numeric, 2)::text, NULL, NULL, NULL, NULL, NULL
FROM public."transaction", m WHERE transaction_state = 'EXPORTER_SUCCESS' AND currency::text = 'USD' AND settlement_date >= m.m0 AND amount > 0
ORDER BY 1, 2;
