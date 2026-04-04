# Phase 5 — Recommendations Engine — Notes

## Implementation

Rule-based engine in `generate_recommendations(status_df, trend_df, profile)`.  Each rule inspects Phase 3 status and Phase 4 trends, then emits zero or more recommendation dicts.

### Recommendation schema

| Field | Type | Description |
|---|---|---|
| category | str | medical, diet, supplement, lifestyle, retest |
| priority | str | high, moderate, low |
| marker_ids | list[str] | Related marker IDs |
| text_pl | str | Recommendation text (Polish) |
| rationale_pl | str | Why this recommendation |
| evidence | str | Source reference |
| confidence | str | How certain (high/moderate/low) |
| medical_escalation | bool | Requires physician review |

### Categories (match HTML report structure)

| Category | Polish label | Description |
|---|---|---|
| medical | Konsultacja lekarska | Out-of-lab-range findings, urgent patterns |
| diet | Dieta | Dietary recommendations |
| supplement | Suplementacja | Supplement recommendations (aware of current stack) |
| lifestyle | Styl życia | Activity, stress, sleep |
| retest | Badania kontrolne | Markers to retest |

## Guardrails

1. **Never diagnose** — all text uses "rozważyć", "omówić z lekarzem", "wskazana diagnostyka"
2. **All out-of-lab values → medical_escalation=True** — 12 markers covered by 4 medical recs
3. **Supplement awareness** — magnez rec notes "mimo suplementacji"; D3+K2 gets positive reinforcement
4. **Patient profile used** — activity level referenced in lifestyle recs

## Results summary

### Distribution (19 recommendations)

| Priority | Count |
|---|---|
| high | 4 |
| moderate | 7 |
| low | 10 |

| Category | Count |
|---|---|
| medical | 4 |
| supplement | 5 |
| lifestyle | 5 |
| retest | 4 |
| diet | 3 |

Medical escalation: 5 recommendations (4 medical + 1 retest for CBC)

### Key recommendations

**High priority:**
1. Morfologia out-of-lab: 9 markers, 6 with worsening trends
2. CBC declining pattern: priority hematology consultation (leukocyty + limfocyty + neutrofile)
3. Hormones out-of-lab: SHBG + Testosteron (with Testosteron worsening trend)
4. CBC retest: control morfologia in 4-6 weeks

**Moderate priority:**
5. Lipid optimization: LDL, Apo B, nie-HDL — dietary fiber, plant sterols
6. HbA1c 5.7%: reduce refined carbs, low GI meals, consider CGM
7. Homocysteine: B6/B12/folate supplementation
8. Magnesium: change form or increase dose (suboptimal despite current supplementation)
9. TSH: lifestyle support (selenium, iodine, sleep, stress)
10-12. Retest: worsening trends with moderate confidence; single-measurement abnormals

**Low priority:**
13. Potassium dietary monitoring
14. Zinc supplementation
15. Vitamin D3 — continue current D3+K2 (positive reinforcement)
16. Selenium supplementation (borderline, relevant for thyroid)
17. Post-meal walks for glycemic control
18. SHBG lifestyle note
19. Thyroid panel expansion (FT3, anti-TPO/anti-TG)

## Design notes

### Supplement stack awareness
Current supplements: D3+K2, magnez, omega-3, kurkumina, probiotyki.
- Magnez rec acknowledges current supplementation and suggests form/dose change
- D3+K2 gets positive reinforcement (Vitamin D3 optimal)
- Omega-3 acknowledged in lipid diet rec ("obecna suplementacja omega-3 wspiera profil lipidowy")
- B-vitamins recommended for homocysteine (not currently supplemented)

### Duplicate labels in medical recs
Neutrofile appears twice in the morfologia medical rec (abs + pct both PONIŻEJ NORMY). The labels are identical ("Neutrofile") which looks redundant. This is a display-level issue — the data correctly captures both expression types. Phase 6 HTML can differentiate with unit suffixes.

### Testosteron "pogorszenie" in medical rec
Testosteron 894 ng/dl flagged POWYŻEJ NORMY with worsening trend. Medical rec now includes clinical nuance: "wysoki testosteron u aktywnego mężczyzny 42 lat może być fizjologicznie prawidłowy — ocenić klinicznie." The SHBG lifestyle rec adds further context.

### Sorting
Recommendations sorted by (priority, category) — high-priority medical items first, low-priority retest items last. Within same priority, category order: medical → diet → supplement → lifestyle → retest.

## Review fixes applied

1. **Cholesterol borderline nuance (M2)** — Cholesterol 191.8 (lab_high=190, 0.9% over) medical rec downgraded to low priority with note: "minimalnie powyżej górnej granicy normy — klinicznie mało istotne przy prawidłowym LDL i Apo B."
2. **Testosterone clinical nuance (M3)** — Medical rec now notes that high testosterone in active 42yo male may be physiologically normal.
3. **eGFR lifestyle rec (M1)** — Added dedicated rec about hydration, creatinine/muscle mass context (KDIGO 2024).
4. **Iron declining trend (M4)** — Added monitoring note for żelazo -16.3% decline in context of low erytrocyty.
5. **Omega-3 acknowledgment (L1)** — Lipid diet rec now mentions current omega-3 supplementation.
6. **Dynamic TSH rationale (L5)** — TSH value and R² in rationale now computed from data, not hardcoded.
7. **Cached trend lookups (L3)** — `_trend()` calls cached in worsening detection loop.
