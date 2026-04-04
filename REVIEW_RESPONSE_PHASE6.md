# Phase 6 External Review — Response

## H1: eGFR falsely described as single measurement

**Agree — valid bug.** The trend pipeline filters out threshold rows (comparator != "") before counting `n_measurements`. eGFR has 7 CSV observations but 6 are thresholds (">60", ">90"), leaving only 1 exact value. The retest rule at line 1462 treats `n_measurements == 1` as "single measurement", producing a false recommendation.

Root cause: `n_measurements` only counts exact values used for regression, but was also used for recommendation wording about observation history. These are semantically different things.

Impact: false recommendation telling the user to retest eGFR despite having 7 observations over 4 years.

## H2: Trend arrows contradict delta_pct sign

**Agree — valid bug.** `_interpret_direction()` maps clinical meaning (poprawa/pogorszenie) based on status context. The `_DIRECTION_ARROWS` map then assigns "↓✗" to pogorszenie. But for markers like LDL (POWYŻEJ OPT), a rising value (+9.8%) IS the worsening — so the arrow shows "↓" (down) next to "+9.8%" (up). The visual is misleading.

Root cause: the arrow encodes clinical direction, but is placed next to a mathematical delta. Two different coordinate systems conflated in one display element.

Impact: 3+ markers show contradictory visual/numeric signals (LDL, TSH, Potas).

## M1: Duplicate bare labels for abs/pct morphology markers

**Agree — valid bug.** The catalog defines both `neutrofile__abs` (label_pl="Neutrofile") and `neutrofile__pct` (label_pl="Neutrofile"). The `_label()` helper returns `label_pl` without disambiguation, so recommendations list "Neutrofile" twice. Same for Limfocyty and Eozynofile.

Root cause: `_label()` doesn't account for expression_type variants sharing the same Polish label.

Impact: ambiguous recommendations — reader can't tell which Neutrofile measurement is meant.

## M2: Cholesterol reassurance contradicts LDL/Apo B findings

**Agree — valid bug.** The softening branch says "klinicznie mało istotne przy prawidłowym LDL i Apo B" without checking whether LDL and Apo B are actually OK. In practice, Apo B is above optimal and the diet section explicitly flags LDL + Apo B. Internal contradiction in the report.

Root cause: the reassurance text was written as a fixed string assuming a favorable lipid profile, but no status lookup guards the claim.

Impact: self-contradictory medical guidance within the same report.
