-- Share rate by cohort: current month's first N full days vs the same N days of last month. Payees excluded.
WITH today AS (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date AS d),
nd AS (SELECT EXTRACT(day FROM d)::int - 1 AS n, date_trunc('month', d)::date AS m0 FROM today),
months AS (
  SELECT m::date AS month_start, (m + (SELECT n FROM nd) * INTERVAL '1 day')::timestamp AS mtd_cutoff
  FROM nd, generate_series(nd.m0 - INTERVAL '1 month', nd.m0, INTERVAL '1 month') AS m
),
users AS (
  SELECT e.id AS exporter_id, MIN(c.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS first_ob
  FROM exporter e JOIN cc_account c ON c.exporter_id = e.id
  WHERE e.id NOT IN ({{EXCLUDED}}) AND NOT EXISTS (SELECT 1 FROM payee p WHERE p.exporter_id = e.id)
  GROUP BY e.id
),
txn_m AS (
  SELECT m.month_start, t.exporter_id,
    MIN(t.settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS first_act,
    MAX(t.settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') FILTER (WHERE t.settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' < m.month_start) AS last_act_before,
    BOOL_OR(t.settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' >= m.month_start AND t.settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' < m.mtd_cutoff) AS txn_this_month
  FROM public."transaction" t CROSS JOIN months m
  WHERE t.transaction_state = 'EXPORTER_SUCCESS' AND t.settlement_date IS NOT NULL GROUP BY 1, 2
),
sig_m AS (
  SELECT m.month_start, r.referrer_exporter_id AS exporter_id,
    BOOL_OR(r.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' < m.month_start) AS referred_before,
    BOOL_OR(r.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' >= m.month_start AND r.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' < m.mtd_cutoff) AS referred_mtd
  FROM referral_relation r CROSS JOIN months m
  WHERE r.referrer_exporter_id IS NOT NULL AND r.is_deleted = false AND r.referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED')
  GROUP BY 1, 2
),
classified AS (
  SELECT m.month_start, u.first_ob, tx.first_act, tx.last_act_before,
    COALESCE(tx.txn_this_month, false) AS txn_this, COALESCE(sg.referred_before, false) AS ref_before, COALESCE(sg.referred_mtd, false) AS ref_mtd
  FROM months m JOIN users u ON u.first_ob < m.mtd_cutoff
  LEFT JOIN txn_m tx ON tx.exporter_id = u.exporter_id AND tx.month_start = m.month_start
  LEFT JOIN sig_m sg ON sg.exporter_id = u.exporter_id AND sg.month_start = m.month_start
),
labelled AS (
  SELECT month_start, ref_mtd,
    CASE WHEN first_act < month_start THEN '1' WHEN first_act >= month_start THEN '2' WHEN first_ob >= month_start THEN '3' ELSE '4' END AS cohort,
    CASE WHEN first_act < month_start AND NOT ref_before THEN '1a' WHEN first_act < month_start AND ref_before THEN '1b' END AS sr,
    CASE WHEN first_act < month_start AND txn_this THEN '1.1'
         WHEN first_act < month_start AND last_act_before >= month_start - INTERVAL '3 months' THEN '1.2'
         WHEN first_act < month_start THEN '1.3' END AS sa
  FROM classified
),
long AS (
  SELECT month_start, cohort AS label, ref_mtd FROM labelled
  UNION ALL SELECT month_start, sr, ref_mtd FROM labelled WHERE sr IS NOT NULL
  UNION ALL SELECT month_start, sa, ref_mtd FROM labelled WHERE sa IS NOT NULL
),
agg AS (SELECT label, month_start, COUNT(*) AS base, COUNT(*) FILTER (WHERE ref_mtd) AS refs FROM long GROUP BY 1, 2)
SELECT c.label, c.base, c.refs AS ref_now, ROUND(100.0 * c.refs / c.base, 2) AS rate_now,
       p.refs AS ref_prev, ROUND(100.0 * p.refs / p.base, 2) AS rate_prev
FROM agg c LEFT JOIN agg p ON p.label = c.label AND p.month_start = (c.month_start - INTERVAL '1 month')::date
WHERE c.month_start = (SELECT m0 FROM nd)
ORDER BY c.label;
