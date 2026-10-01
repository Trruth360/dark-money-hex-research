-- Dark Money Tradecraft: Hex dashboard queries
-- Keep all outputs based on public records and anchored evidence only.

-- 1) Public evidence audit
SELECT
  case_id,
  approved_date,
  county,
  evidence_status,
  anchor_type,
  blocked_fields,
  fine_amount
FROM hygiene_audit
WHERE evidence_status IN ('anchored_public', 'legal_process_dependent')
ORDER BY approved_date DESC;

-- 2) Regional summary by total fines
SELECT
  region_id,
  case_count,
  total_fines,
  avg_fine
FROM regional_summary
ORDER BY total_fines DESC;

-- 3) Monthly region trend
SELECT
  month,
  region_id,
  case_count,
  total_fines
FROM monthly_region_trend
ORDER BY month ASC, total_fines DESC;

-- 4) Accountability score distribution
SELECT
  tier,
  COUNT(*) AS entity_count,
  AVG(total_accountability_deficit) AS avg_deficit,
  SUM(CASE WHEN audit_flag THEN 1 ELSE 0 END) AS audit_required
FROM accountability_scores
GROUP BY tier
ORDER BY avg_deficit DESC;

-- 5) Entities requiring review
SELECT
  entity_name,
  entity_id,
  entity_class,
  state_registered,
  total_accountability_deficit,
  tier,
  audit_flag
FROM accountability_scores
WHERE audit_flag = TRUE
ORDER BY total_accountability_deficit DESC;
