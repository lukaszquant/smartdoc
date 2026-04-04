# Review: PLAN_SPECIALIST_RECS

Date: 2026-04-04

## Findings

### 1. Medium — `filter_label` is defined as an exact canonical match, but several proposed values are shorthand aliases

The revised plan now has a workable split-by-specialist model, but the filtering contract is still slightly off. The data-model section says `filter_label` is used for case-insensitive exact matching against marker `label_pl` values, yet several proposed `filter_label` values are abbreviations or shortened aliases rather than obviously canonical labels.

Examples:
- `OB` for the display label `OB (odczyn Biernackiego)`
- `Kortyzol` for the display label `Kortyzol poranny`
- `Lp(a)` for the display label `Lp(a) — lipoproteina(a)`

Why this matters:
- If a future catalog entry uses the full canonical Polish name instead of the shorthand alias, the exact-match filter will silently fail.
- The field is currently specified as one exact string, not as a list of aliases.

Evidence:
- exact-match contract in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L20-L25)
- shorthand examples in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L53-L54)
- shorthand examples in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L67-L68)
- shorthand example in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L86)

Recommended change:
- Either redefine `filter_label` as a canonical normalized key that must exactly equal the future `label_pl`, or replace it with `filter_aliases: list[str]` and document alias matching explicitly.

### 2. Medium — The plan will likely produce duplicate hematology recommendations with the same extra tests

The current generator already emits two separate medical recommendations for severe CBC decline patterns:
- one general `morfologia` recommendation from the per-group out-of-range loop,
- and one separate high-priority hematology escalation for the CBC pattern.

The revised plan keeps that second rule and explicitly says to attach `specialist_pl="hematolog"` and filtered `morfologia` tests to it as well. That means the report will likely show two hematology recommendations with overlapping markers and the same extra-test list in the common leukopenia / limfopenia / neutropenia case.

Evidence:
- general per-group medical recommendation flow in [generate_report.py](generate_report.py#L1027-L1105)
- separate CBC escalation rule in [generate_report.py](generate_report.py#L1120-L1145)
- plan instruction to enrich the CBC hematology rec in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L210)

Recommended change:
- Either suppress the general `morfologia` specialist rec when the CBC escalation rule fires for the same marker set, or keep the escalation rec but omit duplicated `additional_tests` from one of the two recommendations.

### 3. Low — The verification example for mixed `lipidy` cases is inconsistent with the specialist string defined for D-dimer

The plan maps `d_dimer__direct` to `internista / angiolog`, and the isolated-case verification uses that same route. But the final mixed-case verification bullet says the split result should be `angiolog for D-dimer`, which drops the `internista /` part.

Evidence:
- D-dimer specialist mapping in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L43-L48)
- isolated verification case in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L253)
- mixed-case verification bullet in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L258)

Recommended change:
- Make the verification wording match the actual configured specialist string, or define a separate rule for shortening multi-specialist labels in split cases.

### 4. Low — The plan documents only `mineraly` and `witaminy` as generic-fallback groups, but the catalog has other unmapped groups too

The notes correctly say `mineraly` and `witaminy` stay generic, but the catalog currently also contains `kwasy_tluszczowe`. If any marker in that group is outside lab range, it will also fall back to the generic doctor wording unless you add a specialist rule.

Evidence:
- omission note in [PLAN_SPECIALIST_RECS.md](PLAN_SPECIALIST_RECS.md#L149-L158)
- extra catalog group in [marker_catalog.py](marker_catalog.py#L40-L53)

Recommended change:
- Phrase the fallback behavior generically: any group not present in `GROUP_SPECIALIST` keeps `Omówić z lekarzem` with no specialist or additional tests.

## Bottom Line

No high-severity blockers remain. The revised plan is now implementable in the current recommendation architecture. The remaining gaps are mostly about tightening the filtering contract and avoiding duplicate hematology output once specialist metadata is added.