# Scryfall label cutover runbook

This runbook is for a reviewed release only. It does not authorize a production
database change and must never be used against the application `DATABASE_URL`.

1. Stop new admission and disable the New Cards worker after current work has drained.
2. Take and verify a database backup. Record its restore command outside this repository.
3. Restore that backup into an isolated local database named with `_rehearsal`.
4. Run the migration without `--apply` and review its aggregate count and unresolved intent.
5. Run Apply against the rehearsal target with a new private report path outside this repository:

   ```sh
   uv run python scripts/migrate_scryfall_labels.py \
     --database-url postgresql://.../mtg_helper_rehearsal \
     --apply --report /private/cutover-unresolved.json
   ```

6. Re-run Apply against that rehearsal target. It must report no additional changes and must not
   delete resolved source UUIDs. Compare protected accounts, deck cards and quantities, categories,
   descriptions, plans, collections, and historical recommendation rows before and after.
7. Check matching Scryfall card/tag generation, Oracle-tag route responses, printed-keyword routes,
   source-ID filtering, and absence of retired admin sync routes.
8. Obtain a separate production approval token from the release owner. Only then run the same
   command on the approved production target with `--production-approval`; do not reuse the
   rehearsal report path.
9. Perform the postchecks in step 7, retain the private unresolved report with the release record,
   and re-enable admission and the worker only after they pass.

On any report-write or SQL error, stop. The Apply transaction rolls back data changes; restore the
verified backup rather than attempting a manual repair.
