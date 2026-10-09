# Fresh Sol assessment-only authorization

## Completed

Both new calls completed with no automatic retries, for $0.2423375 conservative estimated cost.
The two-call authorization is consumed. The original timeout remains unpriced/potentially billed.
See [README.md](README.md); the prospective protocol below was frozen before these requests.

The initial Sol run stopped after two plans and one Meren assessment timeout at 120 seconds.
Its usage/bill is unknown and its single-use ledger remains untouched.

The user then explicitly authorized **two additional calls**, **$0.60 additional conservative
estimated cap**, **300-second client timeout**, no automatic retries or production changes:

1. Reissue Meren assessment once.
2. Send Saheeli assessment for the first time.

No planning requests. Same original prompts, schemas, 64-card pools, rules, low reasoning/verbosity,
20k/70k stage byte bounds and 10k review output cap. Request standard processing explicitly.
The copied assessment bytes must match the original. Prior results are referenced by hash, not
fed into the model. Preserve the original potentially billed timeout; do not claim it was free.

Both requests use the same conservative Sol rates ($2.5/M all input, $10/M output). Full reservation
is **$0.55**. The runner enforces this profile's **$0.60** ceiling, not the original $1 global value.
Only timeout and fresh authorization/receipt differ; no prompt tuning or scoring changes.
Each attempt is checkpointed before HTTP, SDK retries are disabled, missing usage/model/tier
pricing stops the run, and an existing new `results.json` blocks repetition/resume.

All previous Sol and Luna/Terra artifacts remain unchanged. No further retry is authorized if
this assessment-only run fails. Whole-Sol cost remains unknown unless the earlier timeout's bill
is established, even if both new calls complete successfully.
