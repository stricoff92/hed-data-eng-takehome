# Workday ingestion

Covers `workday_bronze_daily` and `workday_project_transactions_weekly`.

## How it authenticates

Both jobs call Workday RaaS reports as the integration system user `ISU_Lakehouse`.
The ISU password is stored in Key Vault (`workday-isu-password`) and **expires every
90 days**. It was last rotated on **2026-07-19**.

## Known failure modes

- **Expired ISU password.** Workday answers with HTTP 200 and an empty report rather
  than an authentication error. The job succeeds and writes zero rows. There is no
  exception to catch.
- **Report schema change.** A field renamed in the Workday report surfaces as a null
  column in silver, not as a failure.
- **Tenant maintenance window.** Saturdays 02:00–06:00 America/New_York; runs inside
  the window fail with HTTP 503 and succeed on retry.

## Rotating the password

1. Workday admin resets the ISU password (request through the HRIS queue).
2. Update `workday-isu-password` in Key Vault.
3. Re-run `workday_bronze_daily` from the Jobs UI and confirm `numOutputRows` > 0 in
   the bronze table history.
