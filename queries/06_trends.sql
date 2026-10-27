-- Program-level monthly trend, last 13 months (current month partial).
-- signups / referrers / first_timers exclude {{EXCLUDED}} (internal + flagged); onboardings and activations use the
-- target definition (referee deduped to earliest referrer, {{ALWAYS_EXCLUDED}} only) so they reconcile with the pace block.
-- transactors = exporters with a settled payment that month; sharers = those transactors who also referred that month.
WITH today AS (SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date d),
months AS (SELECT (date_trunc('month', d) - (i||' month')::interval)::date ms FROM today, generate_series(0,12) i),
rr AS (
  SELECT r.referrer_exporter_id ref, r.referee_exporter_id referee, r.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' sat
  FROM referral_relation r
  WHERE r.is_deleted = false AND r.referrer_exporter_id IS NOT NULL AND r.referrer_exporter_id NOT IN ({{EXCLUDED}})
    AND r.referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED')
),
sig AS (SELECT date_trunc('month', sat)::date ms, COUNT(DISTINCT referee) signups, COUNT(DISTINCT ref) referrers FROM rr GROUP BY 1),
ft AS (SELECT date_trunc('month', f)::date ms, COUNT(*) first_timers FROM (SELECT ref, MIN(sat) f FROM rr GROUP BY 1) x GROUP BY 1),
rd AS (
  SELECT DISTINCT ON (referee_exporter_id) referee_exporter_id referee FROM referral_relation
  WHERE referral_state IN ('ONBOARDING_COMPLETE','ACHIEVED') AND is_deleted = false
    AND referrer_exporter_id IS NOT NULL AND referrer_exporter_id NOT IN ({{ALWAYS_EXCLUDED}})
  ORDER BY referee_exporter_id, referral_date
),
ob AS (SELECT exporter_id, MIN(created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') fo FROM cc_account GROUP BY 1),
act AS (SELECT exporter_id, MIN(settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') fa FROM public."transaction" WHERE transaction_state = 'EXPORTER_SUCCESS' GROUP BY 1),
robs AS (SELECT date_trunc('month', ob.fo)::date ms, COUNT(*) ref_onboardings FROM rd JOIN ob ON ob.exporter_id = rd.referee GROUP BY 1),
racts AS (SELECT date_trunc('month', act.fa)::date ms, COUNT(*) ref_activations FROM rd JOIN act ON act.exporter_id = rd.referee GROUP BY 1),
allob AS (SELECT date_trunc('month', fo)::date ms, COUNT(*) all_onboardings FROM ob WHERE exporter_id NOT IN ({{ALWAYS_EXCLUDED}}) GROUP BY 1),
tx AS (SELECT date_trunc('month', settlement_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date ms, exporter_id
       FROM public."transaction" WHERE transaction_state = 'EXPORTER_SUCCESS' AND settlement_date >= now() - INTERVAL '14 months'
         AND exporter_id NOT IN ({{ALWAYS_EXCLUDED}}) GROUP BY 1, 2),
txm AS (SELECT ms, COUNT(*) transactors FROM tx GROUP BY 1),
sharers AS (SELECT date_trunc('month', rr.sat)::date ms, COUNT(DISTINCT rr.ref) sharers FROM rr JOIN tx ON tx.exporter_id = rr.ref AND tx.ms = date_trunc('month', rr.sat)::date GROUP BY 1)
SELECT to_char(m.ms, 'YYYY-MM') AS month, COALESCE(sig.signups, 0) signups, COALESCE(sig.referrers, 0) referrers, COALESCE(ft.first_timers, 0) first_timers,
  COALESCE(robs.ref_onboardings, 0) ref_onboardings, COALESCE(racts.ref_activations, 0) ref_activations, COALESCE(allob.all_onboardings, 0) all_onboardings,
  COALESCE(txm.transactors, 0) transactors, COALESCE(sharers.sharers, 0) sharers
FROM months m LEFT JOIN sig USING (ms) LEFT JOIN ft USING (ms) LEFT JOIN robs USING (ms) LEFT JOIN racts USING (ms)
  LEFT JOIN allob USING (ms) LEFT JOIN txm USING (ms) LEFT JOIN sharers USING (ms)
ORDER BY m.ms;
