# Sync Strategy

How the YC QuickBooks Web Connector performs incremental synchronization safely and efficiently.

## Overview

The goal is to keep Supabase up-to-date with QuickBooks Desktop without:
- Pulling all data every time (too slow, risk of QB timeout)
- Missing changes (stale data)
- Crashing QuickBooks (too many/large requests)

The solution is **incremental sync using `ModifiedDateRangeFilter`** with a **5-minute lookback buffer** and **iterator-based paging** for large batches.

---

## Sync State Table

```sql
CREATE TABLE qb.sync_state (
  company_id      text NOT NULL,
  entity_type     text NOT NULL,
  last_synced_at  timestamptz,     -- when we last successfully synced this entity
  last_full_sync  timestamptz,     -- when we last did a full (no date filter) sync
  status          text DEFAULT 'pending',  -- pending, running, done, error
  records_synced  integer DEFAULT 0,
  error_message   text,
  updated_at      timestamptz DEFAULT now(),
  PRIMARY KEY (company_id, entity_type)
);
```

---

## Sync Types

### Full Sync
- Run on first startup (no `last_synced_at`)
- Optionally triggered manually
- No `ModifiedDateRangeFilter` — pulls ALL records
- Uses iterators always (batch size = 100)
- Can take 10–60 minutes for large company files
- After completion, sets `last_full_sync = now()`

### Incremental Sync
- Default after first full sync
- Uses `ModifiedDateRangeFilter` with:
  - `FromModifiedDate = last_synced_at - 5 minutes` (safety buffer)
  - `ToModifiedDate` = omitted (up to now)
- Only fetches changed records
- Typically completes in seconds to minutes
- After completion, sets `last_synced_at = now()`

### Forced Full Re-sync
- Triggered manually via API: `POST /api/force-full-sync?company=natures-storehouse`
- Resets `last_synced_at = NULL` for all entities
- Next QBWC connection will do a full sync

---

## Iterator Pattern

For large result sets, qbXML supports pagination via iterators.

### How It Works

**First request (Start iterator):**
```xml
<CustomerQueryRq requestID="1" iterator="Start">
  <MaxReturned>100</MaxReturned>
  <ModifiedDateRangeFilter>
    <FromModifiedDate>2024-01-01T00:00:00</FromModifiedDate>
  </ModifiedDateRangeFilter>
</CustomerQueryRq>
```

**First response:**
```xml
<CustomerQueryRs requestID="1" statusCode="0"
  iteratorRemainingCount="450" iteratorID="{a1b2c3d4-...}">
  <!-- 100 CustomerRet elements -->
</CustomerQueryRs>
```

**Continuation request:**
```xml
<CustomerQueryRq requestID="2" iterator="Continue" iteratorID="{a1b2c3d4-...}">
  <MaxReturned>100</MaxReturned>
</CustomerQueryRq>
```

**Continue until `iteratorRemainingCount = 0`.**

### Critical Rules

1. **One iterator at a time.** Do not start a new entity's iterator while another is active. Finish current entity completely before moving to next.
2. **No other requests between Continue calls.** Any intervening qbXML request can invalidate the iterator.
3. **Iterator IDs expire with QB session.** If QBWC disconnects mid-sync, the iterator is lost. Resume from scratch for that entity.
4. **`MaxReturned` can be adjusted per Continue**, but query criteria cannot change.

### Session Flow with Iterators

```
Session: [entity_queue = [Customers, Vendors, Invoices, ...]]

Tick 1: sendRequestXML → CustomerQuery iterator=Start
        receiveResponseXML ← 100 customers, remaining=450, iterID=X
        → save iterID to session, upsert 100 customers
        → return 5 (5% done, more work pending)

Tick 2: sendRequestXML → CustomerQuery iterator=Continue iterID=X
        receiveResponseXML ← 100 customers, remaining=350
        → return 10

... (5 more ticks) ...

Tick 7: sendRequestXML → CustomerQuery iterator=Continue iterID=X
        receiveResponseXML ← 50 customers, remaining=0
        → clear iterID, mark Customers done, move to Vendors
        → return 15

Tick 8: sendRequestXML → VendorQuery iterator=Start
...

Tick N: sendRequestXML → "" (empty, all entities done)
        → return 100
        QBWC calls closeConnection
```

---

## Handling Deletions

QuickBooks does NOT report deletions via qbXML. Records simply disappear from query results.

**Strategy:**
1. **Soft-delete detection via periodic full sync:** Once a week, run a full sync. After completing, compare received `qb_list_id`/`qb_txn_id` sets against what's in Supabase. Records in Supabase but not in QB are candidates for soft-deletion.
2. **Mark as inactive, not hard-delete:** Set `is_active = false` and `deleted_in_qb_at = now()` rather than deleting rows. Preserves referential integrity.
3. **For transactions:** QB transactions can be voided but not deleted from history. Voided transactions appear with `TotalAmount = 0` and a "VOID" memo.

---

## Batch Size Tuning

Default `MaxReturned = 100`. Adjust based on:

| Entity | Recommended MaxReturned | Reason |
|--------|------------------------|--------|
| Accounts | 200 | Small records |
| Customers | 100 | Medium records with addresses |
| Vendors | 100 | Medium records |
| Items | 100 | Medium records |
| Invoices | 50 | Large records with line items |
| SalesReceipts | 50 | Large records |
| JournalEntries | 50 | Multiple lines per entry |
| TimeTracking | 200 | Small records |

Set per-entity in `config/companies.yaml` or use defaults.

---

## Session Timeout and Recovery

QBWC has a configurable polling interval (set in `.qwc` via `<RunEveryNMinutes>`). Between polls, QB can close.

**Recovery scenarios:**

| Scenario | Detection | Recovery |
|---------|----------|---------|
| QB closed mid-iterator | Iterator error in response | Restart entity from beginning of current page range |
| Service restarted mid-session | Ticket not found in session store | Re-authenticate and restart from last committed sync_state |
| Supabase down mid-sync | Upsert exception | Retry with backoff; do not advance sync_state until committed |
| QB response error (statusCode != 0) | Parse response status | Log error, skip entity, continue with next entity |

---

## Progress Tracking

The `receiveResponseXML` return value (0–100) is calculated as:

```python
entities_total = len(sync_queue_initial)
entities_done = entities_total - len(sync_queue_remaining)
# Account for iterator progress within current entity
current_entity_progress = (
    (initial_count - iterator_remaining) / initial_count
    if initial_count > 0 else 1.0
)
overall_progress = int(
    ((entities_done + current_entity_progress) / entities_total) * 99
)
# Return 100 only when truly done
return min(overall_progress, 99) if sync_queue_remaining else 100
```

---

## Scheduling Recommendations

| Company | Recommended Interval | Rationale |
|---------|--------------------|---------| 
| Nature's Storehouse | Every 15 minutes during business hours, hourly overnight | Active retail, POS transactions |
| ADK Fragrance Farm | Every 30 minutes | Lower transaction volume |

Configure in `<RunEveryNMinutes>` in the `.qwc` file.

---

## Data Freshness SLAs

With 15-minute polling:
- New transactions: visible in Supabase within ~20 minutes
- Modified records: visible within ~20 minutes
- Deleted records: visible within ~7 days (weekly full sync)
- New customers/vendors: visible within ~20 minutes

---

## Monitoring

The service exposes a health endpoint:

```
GET /health
→ { "status": "ok", "version": "1.0.0" }

GET /api/sync-status
→ {
    "natures-storehouse": {
      "last_sync": "2024-01-15T14:30:00Z",
      "status": "done",
      "entities": {
        "customers": { "last_synced_at": "...", "records": 1247 },
        "invoices": { "last_synced_at": "...", "records": 45821 },
        ...
      }
    }
  }
```
