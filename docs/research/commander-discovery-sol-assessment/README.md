# Sol completed assessments — stronger spot checks, not a complete overall pass

## Now

Both freshly authorized assessment requests completed, no automatic retries, standard processing,
within the $0.60 additional estimated cap. Cost for this two-call run: **$0.2423375**.
Both fresh calls are consumed; no further call/retry is authorized.

Together with the two earlier completed plans, **known** conservative estimated Sol cost is
**$0.2746775**. Whole-Sol total remains **unknown**: the original Meren timeout was potentially
billed and returned no usage. It remains preserved in the [original partial run](../commander-discovery-sol/README.md).
There were **five issued Sol requests across two authorizations**: two completed plans, one
unpriced timeout, and two completed new assessments. Do not present this as a four-call clean run.

[Actual thirty ranked suggestions](outputs.md) · [Fresh authorization protocol](protocol.md)

## Same-pool comparison

Prompts, schemas, rules, candidate order and data match the previous Luna/Terra requests. Only a
fresh receipt, explicitly pinned standard tier and the 300-second client timeout were used.
Independent Sol planning/discovery remains in the original report; no new candidate was inserted
into these assessment pools and no previous outputs/human findings were supplied to the model.

| Commander/model | Assessment latency | Quote/identity-grounded assessments | Complete validation |
| --- | ---: | ---: | --- |
| Meren/Luna | 58.4 s | 61/64 | no |
| Meren/Terra | 75.7 s | 58/64 | no |
| Meren/Sol | 153.4 s | 64/64 | **yes** |
| Saheeli/Luna | 61.8 s | 55/64 | no |
| Saheeli/Terra | 80.0 s | 46/64 | no |
| Saheeli/Sol | 151.6 s | 61/64 | no |

Grounding/identity conformance is **not semantic accuracy**. All thirty Sol ranked IDs were bare
valid keys with accepted evidence. Saheeli failed full coverage despite a completed provider status:

- `C07` / Plasma Caster: the equip quote has an extra Arabic glyph; literal grounding fails.
- `C09` / Wheel of Potential: assessed twice, both falsely claiming the supplied key/data was absent,
  with no candidate evidence. Wheel was present in the actual input.
- `C63` / Torpor Orb: no assessment. Do not invent Sol's Torpor Orb verdict or silently repair IDs.

The duplicated and missing rows are preserved and flagged, not reissued for better scores.

## Targeted strategic/rules review

Sol's returned explanations are more nuanced on several inspected connections than the earlier
models' explanations. This is a small targeted regression comparison, not certification of every
judgment or a statistically established model ranking.

### Meren

- Yawgmoth explains sacrifice/draw/control **plus discard stocking targets and experience proliferation**.
- Cankerbloom distinguishes sacrifice-based removal, the experience gained by its own death, and
  proliferating an experience counter once one exists.
- Evolution Sage connects player experience to landfall, with proposed Elder/Solemn support.
- Beast Whisperer is not dismissed: casting creatures returned to hand can help, but direct
  battlefield returns/tokens do not trigger its draw.
- Grim Haruspex explicitly excludes tokens, opponents' creatures and its own death.
- Spore Frog notes that one return on your end step does not automatically protect all opponents'
  combats in a multiplayer cycle.

Cankerbloom/Evolution Sage were still forced/shared inputs, **not Sol's independent discoveries**.
The planner had missed proliferation, and the reviewer received the proliferate rules definition.
Correct assessment does not retrospectively repair admission.

### Saheeli

- Whirler: casting with Saheeli plus entry gives four energy; a combat copy's entry refunds the
  three-energy payment. Neither prior reviewer explicitly gave this copy-refund explanation.
- Sundial: end the turn with the sacrifice trigger on the stack; ending earlier postpones it.
  Sol independently nominated it in planning, unlike the earlier forced-diagnostic-only admission.
- Second Harvest: copied 5/5/haste values persist, but the separate delayed sacrifice is not copied.
- Brudiclad: resolve Saheeli first, then transform other tokens; distinguish the external sacrifice
  instruction and warn about legendary templates.
- Solemn/Wurmcoil: copies are 5/5; Wurmcoil copy death leaves tokens. Sai's draw costs two mana,
  not the four mana claimed by Luna.
- Panharmonicon: entry triggers only, not Saheeli's cast/combat triggers or token creation itself.
- Hangarback: copied counters/original X are not inherited; a hasty copy can tap to add a counter,
  while a zero-counter copy produces no Thopters when sacrificed.
- Inventor's Axe: the one-mana original generates three energy with Saheeli; a creature Equipment
  copy cannot remain attached. Shuri's sorcery timing is not bypassed by haste.
- Giant-Man: ordinary temporary combat copies cannot boost the next first-main trigger without
  retention; Prepared/face access remains explicitly uncertain when rules are missing.

These explanations were checked against supplied source facts and applicable generic rules.
They support a stronger advisor hypothesis, not permanent card capability labels or an automatic
proof of whole packages. Full returned assessments remain available in `summary.json`/`results.json`.

## Practical conclusion

**Sol currently looks stronger for nuanced fact-fed assessment in these cases.** It also fixed
some planning wording and independently pursued Saheeli retention. Its Meren–proliferate planning
omission, sampling/admission limits and Saheeli coverage failure remain.

The tradeoff is substantial latency: roughly 2× Terra and 2.5× Luna for the same 64-card assessment.
The successful requests took longer than the original 120-second client timeout, explaining the
need for the separate longer-window test. This large workload is not the deployed eight-card New
Cards batch; do not claim it reproduces the application lag. Keep ordinary browsing independent
of model completion. No production model switch or broad implementation was approved/performed.

## Artifacts and checks

`inputs.json` freezes this fresh two-call authorization and the prior receipt hash;
`assessment-inputs.json` is byte-identical to both older copies. `results.json` preserves both
new requests/usage, `summary.json` preserves coverage failures, and `retrieval.json` references
previous discovery rather than fabricating new planning. All old JSON evidence remains unchanged.

**104 offline tests** passed, scoped Ruff/format and `ty` passed, function/parameter bounds passed.
The smaller-budget guard was mutation-tested: restoring the old $1 remaining-spend comparison
made the new $0.60 test fail. One independent read-only boundary review found no supported blockers.
That review was not certification of Magic judgments.

Offline replay from `backend/`:

```bash
uv run --no-sync python -m scripts.commander_discovery_sol_assessment_check --summarize
```

**Do not delete either Sol `results.json` or make more paid calls without new authorization.**
