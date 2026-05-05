# YC QB Connector — PII Policy

**Owner:** Clark Maine
**Established:** 2026-05-05
**Scope:** every entity the YC QB Web Connector pulls from QuickBooks Desktop
into the `vynzrvgoyqorqxogjrgw` Supabase project (companies: adk_fragrance,
yc_works, maine_and_maine, yc_consulting).

## Rule

> "I don't want any PII in the final data — just name but not phone numbers,
> socials etc." — Clark, 2026-05-05

PII is dropped **at the parser layer**, before any value reaches Postgres or
logs. We do not store-and-then-mask; the fields never enter the system.

## Why this is enforceable here (not just a TODO)

1. The connector parser only emits the fields it's told to emit. It does not
   bulk-serialize the QB element to JSON. So omitting a field at the parser
   means the field never exists downstream.
2. There is no `raw_response` JSONB column on payroll/employee tables — the
   only persisted fields are the operational columns explicitly listed in the
   schema migration.
3. Logs are configured to redact common PII patterns (SSN-like
   `\d{3}-\d{2}-\d{4}`, credit-card-like sequences) at the log writer.

## Per-entity policy

### Employees (`{schema}.employees`)

| Field (QB qbXML) | Status | Stored as | Notes |
|---|---|---|---|
| `ListID` | KEEP | `qb_list_id` | Stable identifier. |
| `Name` | KEEP | `name` | Display name (often "First Last"). |
| `Salutation`, `FirstName`, `MiddleName`, `LastName`, `Suffix` | KEEP | individual cols | Name only — no DOB, no SSN. |
| `JobTitle` | KEEP | `job_title` | Operational. |
| `EmployeeType` | KEEP | `employee_type` | Regular / Statutory / Owner / Officer. |
| `HiredDate`, `ReleasedDate` | KEEP | `hired_date`, `released_date` | Tenure analysis. |
| `IsActive` | KEEP | `is_active` | Operational. |
| `TimeCreated`, `TimeModified`, `EditSequence` | KEEP | metadata cols | QB lineage. |
| `EmployeeAddress` (home) | **DROP** | — | Home address is PII. |
| `Phone` | **DROP** | — | Treated as personal landline. |
| `Mobile` | **DROP** | — | Personal cell. |
| `Email` | **DROP** | — | Personal email. |
| `Gender` | **DROP** | — | Identity, not operational. |
| `ExternalGUID` | **DROP** | — | Tracking ID, no analytical value. |
| `SSN` | **NEVER REQUESTED** | — | We don't even fetch this field from qbXML. |
| `BankAccountInfo`, routing/account | **NEVER REQUESTED** | — | Same — never fetched. |
| `DOB` | **NEVER REQUESTED** | — | If we need tenure-style "year of birth," derive elsewhere. |
| `DriverLicense`, `Passport` | **NEVER REQUESTED** | — | |

### Paychecks (`{schema}.paychecks`, `{schema}.paycheck_lines`)

| Field | Status | Notes |
|---|---|---|
| `TxnID`, `RefNumber`, `TxnNumber`, `TxnDate` | KEEP | Operational. |
| `EmployeeRef` (ListID + name) | KEEP | Name only — full name is acceptable per Clark's rule ("just name"). |
| `AccountRef` (payroll account) | KEEP | Operational. |
| `GrossEarnings`, `NetPaycheck` | KEEP | Compensation analysis. |
| `PayPeriodStartDate`, `PayPeriodEndDate` | KEEP | Operational. |
| `Memo` | KEEP | Sometimes contains job/department notes. Audit periodically — if employees write personal notes here we'd want to scrub. |
| Line: `WageItemRef`, `Hours`, `Rate`, `Amount` | KEEP | Compensation data. |
| Line: `ClassRef`, `CustomerRef` | KEEP | Job costing. |
| `IsToBePrinted`, `IsPending`, `IsVoid` | KEEP | Operational. |
| Bank account / routing on direct deposit | **NEVER REQUESTED** | Not extracted. |
| W-4 raw data | **NEVER REQUESTED** | Not extracted. |

### Payroll Items (`{schema}.payroll_items_wage`, `{schema}.payroll_items_non_wage`)

These are item-type definitions (HourlyRegular, FederalTax, 401k Deduction,
etc.). No employee-level PII. All fields KEEP — they're configuration, not
personal data.

### Customers (`{schema}.customers`)

These are **businesses**, not people. Per Clark's rule, business addresses
and business phone numbers are KEEP. We do NOT separately try to detect
"this customer happens to be a sole proprietor whose home address is also
their business address" — if QB has them as a customer, we treat the
contact info as business contact info.

### Vendors (`{schema}.vendors`)

Same rule as customers — business contact info is KEEP. Vendor's `TaxIdent`
(EIN) is also KEEP since it's an issued business identifier.

If a vendor row contains an SSN in the `TaxIdent` field (sole proprietor
1099 contractors), we would need to scrub. **Action item:** spot-check this
on the existing `adk_fragrance.vendors` table before replicating to other
schemas. (Tracked in Step E audit.)

### Time tracking (`{schema}.time_tracking`)

Hours by employee + customer/job + class. Employee NAME (KEEP) + hours
(KEEP). No personal contact info in this entity at the qbXML schema level.

## Logging

`src/utils/logging.py` should redact:
- SSN-like patterns: `\b\d{3}-\d{2}-\d{4}\b` and `\b\d{9}\b` when context
  suggests SSN
- Credit-card-like 13-19 digit sequences

(Action: verify this is actually enabled in the connector. If not, add a
filter. Tracked in this PR.)

## What changed 2026-05-05

1. **Migration `strip_employee_pii_columns` applied** — dropped
   `address`, `phone`, `mobile`, `email`, `gender`, `external_guid` columns
   from `employees` in all 4 schemas. 21 rows of `adk_fragrance` employees
   had these populated; column drop is irreversible (no backup needed —
   data was sourced from QB and can be re-derived without these fields if
   ever needed).
2. **`parse_employee()` updated** in `src/qbxml/parsers.py` to stop
   extracting these fields. Comments name what was dropped and why.

## Future entity additions

Any time we add a new EntityDef + parser, the parser MUST be reviewed
against this doc BEFORE the code merges. PR review checklist:

- [ ] Does this entity expose any field listed under "DROP" in this doc?
- [ ] If yes, is the field omitted at the parser layer?
- [ ] Does the schema migration avoid creating a column for the dropped
      field?
- [ ] If a new field type appears that isn't in this doc, classify it as
      KEEP/DROP and update this doc in the same PR.
