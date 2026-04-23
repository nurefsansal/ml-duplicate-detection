# Splink Primary Comparison Fix

## What Was Wrong Before

- Splink was already producing match probabilities, but the frontend was still reading several field-level values from legacy heuristic features.
- Because of that hybrid path, the UI could show misleading breakdowns.
- The email mismatch bug came from two issues together:
  - backend field display was not consistently mapped from the actual Splink email comparison basis
  - frontend admin scoring was still reading legacy `email_similarity` as if it were already a percent
- Some pages were still expecting old `L_/R_` response keys.
- `MukerrerKayitlar` also had hardcoded score breakdown values, so many pairs looked artificially similar.

## How It Works Now

- Splink is the primary comparison engine for:
  - full name
  - first name
  - surname
  - TCKN
  - phone
  - email
  - city
  - address as supporting-only text
- Each duplicate pair now returns explicit `fieldComparisons` objects with:
  - raw values
  - normalized values
  - comparison method
  - comparison result
  - score from 0 to 100
  - exact match flag
  - notes
- The legacy `features` dict is still present, but it is now derived from Splink-first comparisons in the normal path instead of overriding them.
- Frontend pages now render `fieldComparisons` and `splinkMatchProbability` directly.

## What Remains Rule-Based

- Business safety rules still run after Splink scoring.
- These rules are responsible for the final decision layer:
  - `tc_conflict`
  - household/shared contact risk
  - review downgrade logic
  - conservative merge protection
- Rules now add `riskFlags`, `ruleReasons`, and final decision outputs.
- Rules do not fake field-level match displays anymore.

## Fallback Behavior

- Normal path:
  - `decisionSource = "splink_plus_rules"`
- Fallback path:
  - `decisionSource = "fallback_legacy"`
- Legacy blocking/features/model flow is still available only if Splink completely fails.
- Splink training steps were hardened for small datasets, so tiny test batches no longer fall into legacy mode just because EM or prior estimation is underpowered.

## Files Changed

- `backend/services/splink_service.py`
- `backend/services/rule_matching_service.py`
- `backend/api/routes/admin.py`
- `backend/schemas/responses.py`
- `frontend/src/services/api.ts`
- `frontend/src/utils/duplicatePairView.ts`
- `frontend/src/components/feature/FieldComparisonsPanel.tsx`
- `frontend/src/pages/MukerrerTespit/index.tsx`
- `frontend/src/pages/MukerrerKayitlar/index.tsx`
- `frontend/src/pages/YoneticiOnayi/index.tsx`
- `backend/tests/test_splink_field_comparisons.py`
