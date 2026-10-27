-- One row per gift campaign in config.campaign_history: signups, referrers, onboarded, achieved, gifts claimed.
-- Signups exclude {{EXCLUDED}}. Rows tagged before the campaign was created exist (re-tagging); the page uses created_d as the start.
WITH c AS (SELECT id, name, is_active, created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS created_ist FROM referral_campaign WHERE id IN ({{CAMPAIGN_HISTORY_IDS}})),
rr AS (
  SELECT r.campaign_id, r.referrer_exporter_id ref, r.referee_exporter_id referee, r.referral_state::text st, r.referral_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' sat
  FROM referral_relation r
  WHERE r.is_deleted = false AND r.referrer_exporter_id IS NOT NULL AND r.referrer_exporter_id NOT IN ({{EXCLUDED}})
    AND r.referral_state IN ('SIGNUP_COMPLETE','ONBOARDING_COMPLETE','ACHIEVED') AND r.campaign_id IN ({{CAMPAIGN_HISTORY_IDS}})
),
cl AS (SELECT k.campaign_id, COUNT(*) FILTER (WHERE k.status = 'CLAIMED') claimed, string_agg(DISTINCT m.label, ', ') gifts
       FROM referral_milestone_claim k JOIN referral_campaign_milestone m ON m.id = k.milestone_id WHERE k.is_deleted = false GROUP BY 1),
agg AS (SELECT campaign_id, MIN(sat)::date first_d, MAX(sat)::date last_d, COUNT(*) signups, COUNT(DISTINCT ref) referrers,
  COUNT(*) FILTER (WHERE st IN ('ONBOARDING_COMPLETE','ACHIEVED')) onboarded, COUNT(*) FILTER (WHERE st = 'ACHIEVED') achieved FROM rr GROUP BY 1)
SELECT c.id, c.name, c.is_active, c.created_ist::date::text AS created_d, agg.first_d::text AS first_d, agg.last_d::text AS last_d,
  COALESCE(agg.signups, 0) signups, COALESCE(agg.referrers, 0) referrers, COALESCE(agg.onboarded, 0) onboarded, COALESCE(agg.achieved, 0) achieved,
  COALESCE(cl.claimed, 0) claimed, cl.gifts
FROM c LEFT JOIN agg ON agg.campaign_id = c.id LEFT JOIN cl ON cl.campaign_id = c.id
ORDER BY c.created_ist;
