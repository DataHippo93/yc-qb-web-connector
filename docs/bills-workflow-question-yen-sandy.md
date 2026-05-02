# Quick Q for Yen / Sandy — QB Bills workflow at ADKFF

**Context for Clark before sending:** The connector is reporting roughly zero
"Bills" entries in QB for ADKFF since mid-2024 even though Checks and Credit
Card Charges are flowing normally. The drop-off looks gradual (43→42→41→44
per quarter through 2023, then 21→2→1→0 through 2024) which is the pattern
of a workflow change, not a connector bug. Need to confirm before locking
in the assumption.

---

## Short version (text / Signal)

> Hey — quick accounting question. When a vendor bills us, are you still
> entering it as a "Bill" in QuickBooks (and then paying it later as
> "Pay Bills"), or are you skipping that and just entering the payment
> directly as a Check or Credit Card Charge? Just want to confirm the
> current process — no problem either way, I'm cleaning up some reporting.

---

## Slightly longer version (email)

**Subject:** Quick QuickBooks process question — Bills vs. Checks

Hi Yen / Sandy,

I'm cleaning up the financial reporting pipeline for ADKFF and noticed
that we have very few "Bill" entries in QuickBooks since mid-2024. Looks
like nearly all vendor activity is going through Checks and Credit Card
Charges directly, which is fine — I just want to confirm that's the
intended process now, so I can adjust how we're aggregating expenses
on the reporting side.

Two quick questions:

1. **Are you still using the Bill / Pay Bills workflow at all?** (i.e. enter
   a Bill when the invoice arrives, then "Pay Bills" later)

2. **Or have you switched to entering vendor payments directly** as Checks
   or Credit Card Charges (skipping the Bill step)?

No issue either way — totally normal for a small operation to simplify to
direct payment entry. I just want to make sure my reports aren't pulling
from the wrong place.

Thanks,
Clark

---

## What to do with the answer

- **If they say "we still use Bills"** → it's a connector issue. Open a ticket
  to investigate why the BillQueryRq isn't returning recent bills (likely a
  QB-side filter, permission, or schema change). Use the new
  `POST /backfill/adk_fragrance/bills` endpoint with `filter_type=txn` and
  a 2024-Q3 to today window to test whether QB will return bills for that
  range. If it does, the original sync was missing them; fix the sync.
- **If they say "we switched to Checks/CC"** → no connector change needed.
  Document the workflow change in `docs/qbxml-entities.md` and tell anyone
  doing OpEx analysis to use the new `<schema>.expenses_unified` view
  instead of `bill_lines` directly. The view already aggregates
  bills + checks + credit cards + journal entries.
- **If the answer is mixed** ("we use Bills sometimes, mostly Checks") →
  same answer as above: use `expenses_unified` for OpEx, keep the bills
  sync running so we capture the occasional bill they do enter.
