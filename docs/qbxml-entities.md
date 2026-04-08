# qbXML Entities Reference

Complete list of QuickBooks entities accessible via qbXML through the Web Connector. Each entry includes the query request name, filter support, and iterator support.

## List Objects

List objects represent master data (not transactions). They have a `ListID` as primary key and support `ModifiedDateRangeFilter`.

| Entity | QueryRq Name | ModifiedFilter | Iterator | Notes |
|--------|-------------|----------------|----------|-------|
| Account | `AccountQueryRq` | ✅ | ✅ | Chart of Accounts. Types: Bank, AR, AP, CreditCard, OtherCurrentAsset, FixedAsset, OtherAsset, OtherCurrentLiab, LongTermLiab, Equity, Income, CostOfGoodsSold, Expense, OtherExpense, NonPosting |
| Class | `ClassQueryRq` | ✅ | ✅ | Tracking classes for P&L segmentation |
| Customer | `CustomerQueryRq` | ✅ | ✅ | Includes sub-customers (jobs). `IsActive`, `ParentRef` for hierarchy |
| CustomerMessage | `CustomerMessageQueryRq` | ✅ | ✅ | Pre-set messages on invoices/sales receipts |
| CustomerType | `CustomerTypeQueryRq` | ✅ | ✅ | Customer classification labels |
| Employee | `EmployeeQueryRq` | ✅ | ✅ | Requires payroll access. SSN masked unless admin |
| ItemDiscount | `ItemDiscountQueryRq` | ✅ | ✅ | Discount line items |
| ItemFixedAsset | `ItemFixedAssetQueryRq` | ✅ | ✅ | Fixed asset items |
| ItemGroup | `ItemGroupQueryRq` | ✅ | ✅ | Item groups (pre-set bundles) |
| ItemInventory | `ItemInventoryQueryRq` | ✅ | ✅ | Inventory items with qty on hand, cost |
| ItemInventoryAssembly | `ItemInventoryAssemblyQueryRq` | ✅ | ✅ | Assembly/BOM items |
| ItemNonInventory | `ItemNonInventoryQueryRq` | ✅ | ✅ | Non-inventory items (services billed as items) |
| ItemOtherCharge | `ItemOtherChargeQueryRq` | ✅ | ✅ | Misc charge items |
| ItemPayment | `ItemPaymentQueryRq` | ✅ | ✅ | Payment method items |
| ItemSalesTax | `ItemSalesTaxQueryRq` | ✅ | ✅ | Sales tax items with rate |
| ItemSalesTaxGroup | `ItemSalesTaxGroupQueryRq` | ✅ | ✅ | Combined tax groups |
| ItemService | `ItemServiceQueryRq` | ✅ | ✅ | Service items |
| ItemSubtotal | `ItemSubtotalQueryRq` | ✅ | ✅ | Subtotal line item type |
| JobType | `JobTypeQueryRq` | ✅ | ✅ | Job classification for contractors |
| OtherName | `OtherNameQueryRq` | ✅ | ✅ | Names that aren't Customer/Vendor/Employee |
| PaymentMethod | `PaymentMethodQueryRq` | ✅ | ✅ | Cash, Check, Credit Card, etc. |
| PriceLevel | `PriceLevelQueryRq` | ✅ | ✅ | Custom pricing tiers per customer |
| SalesRep | `SalesRepQueryRq` | ✅ | ✅ | Sales representative list |
| SalesTaxCode | `SalesTaxCodeQueryRq` | ✅ | ✅ | Taxable/non-taxable codes |
| ShipMethod | `ShipMethodQueryRq` | ✅ | ✅ | Shipping methods |
| StandardTerms | `StandardTermsQueryRq` | ✅ | ✅ | Payment terms (Net 30, etc.) |
| DateDrivenTerms | `DateDrivenTermsQueryRq` | ✅ | ✅ | Date-based payment terms |
| Template | `TemplateQueryRq` | ✅ | ✅ | Invoice/form templates |
| ToDo | `ToDoQueryRq` | ✅ | ✅ | QB reminder/to-do list items |
| UnitOfMeasureSet | `UnitOfMeasureSetQueryRq` | ✅ | ✅ | Units of measure (requires UOM feature) |
| Vendor | `VendorQueryRq` | ✅ | ✅ | Vendors/suppliers |
| VendorType | `VendorTypeQueryRq` | ✅ | ✅ | Vendor classification labels |
| WorkersCompCode | `WorkersCompCodeQueryRq` | ✅ | ✅ | Workers' comp classification |

---

## Transaction Objects

Transaction objects represent financial events. They have a `TxnID` as primary key and support `ModifiedDateRangeFilter` and/or `TxnDateRangeFilter`.

| Entity | QueryRq Name | ModifiedFilter | TxnDateFilter | Iterator | Notes |
|--------|-------------|----------------|---------------|----------|-------|
| ARRefundCreditCard | `ARRefundCreditCardQueryRq` | ✅ | ✅ | ✅ | Refunds to credit cards on AR |
| Bill | `BillQueryRq` | ✅ | ✅ | ✅ | Vendor bills (AP) |
| BillPaymentCheck | `BillPaymentCheckQueryRq` | ✅ | ✅ | ✅ | Bill payments via check |
| BillPaymentCreditCard | `BillPaymentCreditCardQueryRq` | ✅ | ✅ | ✅ | Bill payments via credit card |
| BuildAssembly | `BuildAssemblyQueryRq` | ✅ | ✅ | ✅ | Inventory assembly builds |
| Charge | `ChargeQueryRq` | ✅ | ✅ | ✅ | Statement charges |
| Check | `CheckQueryRq` | ✅ | ✅ | ✅ | Checks written |
| CreditCardCharge | `CreditCardChargeQueryRq` | ✅ | ✅ | ✅ | Credit card expenses |
| CreditCardCredit | `CreditCardCreditQueryRq` | ✅ | ✅ | ✅ | Credit card credits/refunds |
| CreditMemo | `CreditMemoQueryRq` | ✅ | ✅ | ✅ | Customer credit memos |
| Deposit | `DepositQueryRq` | ✅ | ✅ | ✅ | Bank deposits |
| Estimate | `EstimateQueryRq` | ✅ | ✅ | ✅ | Customer estimates/quotes |
| InventoryAdjustment | `InventoryAdjustmentQueryRq` | ✅ | ✅ | ✅ | Manual inventory adjustments |
| Invoice | `InvoiceQueryRq` | ✅ | ✅ | ✅ | Customer invoices — most important! |
| ItemReceipt | `ItemReceiptQueryRq` | ✅ | ✅ | ✅ | Received items (from POs) |
| JournalEntry | `JournalEntryQueryRq` | ✅ | ✅ | ✅ | General journal entries |
| PurchaseOrder | `PurchaseOrderQueryRq` | ✅ | ✅ | ✅ | Purchase orders to vendors |
| ReceivePayment | `ReceivePaymentQueryRq` | ✅ | ✅ | ✅ | Customer payments received |
| SalesOrder | `SalesOrderQueryRq` | ✅ | ✅ | ✅ | Sales orders (if enabled) |
| SalesReceipt | `SalesReceiptQueryRq` | ✅ | ✅ | ✅ | Cash sales receipts |
| TimeTracking | `TimeTrackingQueryRq` | ✅ | ✅ | ✅ | Time tracking entries |
| Transfer | `TransferQueryRq` | ✅ | ✅ | ✅ | Account transfers |
| VendorCredit | `VendorCreditQueryRq` | ✅ | ✅ | ✅ | Vendor credits |

---

## Special/Report Objects

These are queried differently — they return computed/summary data, not raw transaction lists.

| Entity | QueryRq Name | Notes |
|--------|-------------|-------|
| Company | `CompanyQueryRq` | Company info, address, EIN |
| Host | `HostQueryRq` | QB version, supported qbXML versions |
| Preferences | `PreferencesQueryRq` | QB preferences (accounting method, etc.) |
| GeneralSummaryReport | `GeneralSummaryReportQueryRq` | P&L, Balance Sheet, etc. (not recommended for raw data) |
| GeneralDetailReport | `GeneralDetailReportQueryRq` | Detailed transaction reports |
| CustomSummaryReport | `CustomSummaryReportQueryRq` | Custom report builder |
| CustomDetailReport | `CustomDetailReportQueryRq` | Custom detail report |
| BudgetSummaryReport | `BudgetSummaryReportQueryRq` | Budget vs actual |

> **Note:** Report queries are slow and expensive. Prefer entity queries for raw data. Use reports only for pre-aggregated views if needed.

---

## Payroll Entities

Payroll requires special QB permissions. These may not be accessible depending on QB edition and user permissions.

| Entity | QueryRq Name | Notes |
|--------|-------------|-------|
| PayrollDetailReport | `PayrollDetailReportQueryRq` | Payroll transaction detail |
| Employee | `EmployeeQueryRq` | Basic employee info |
| TimeTracking | `TimeTrackingQueryRq` | Hours worked |

> Payroll transactions themselves (paychecks, payroll liabilities) are not directly queryable via qbXML in most editions. Access is through reports only.

---

## Sync Priority Order

Entities should be synced in this order to ensure FK relationships are satisfied:

### Phase 1: Reference Data (Lists)
1. Accounts
2. Classes
3. SalesTaxCodes
4. PaymentMethods
5. ShipMethods
6. StandardTerms / DateDrivenTerms
7. CustomerTypes / VendorTypes / JobTypes
8. Customers (with jobs/sub-customers)
9. Vendors
10. Employees
11. SalesReps
12. Items (all types: Service, Inventory, NonInventory, OtherCharge, Group, Assembly, Discount, SalesTax)
13. Templates
14. PriceLevels
15. UnitOfMeasureSets

### Phase 2: Transactions (oldest first)
16. PurchaseOrders
17. ItemReceipts
18. Bills
19. BillPaymentChecks
20. BillPaymentCreditCards
21. VendorCredits
22. Estimates
23. SalesOrders
24. Invoices
25. SalesReceipts
26. CreditMemos
27. ReceivePayments
28. Deposits
29. Checks
30. CreditCardCharges
31. CreditCardCredits
32. JournalEntries
33. Transfers
34. InventoryAdjustments
35. BuildAssemblies
36. TimeTracking
37. Charges

### Phase 3: Metadata
38. Company
39. Host
40. Preferences

---

## qbXML Version Compatibility

| qbXML Version | QB Desktop Version | Key Additions |
|--------------|-------------------|---------------|
| 1.0 – 2.0 | QB 2002–2004 | Basic entities |
| 3.0 – 6.0 | QB 2004–2006 | Iterator support added in 2.0 |
| 8.0 – 10.0 | QB 2008–2010 | UOM, Assembly items |
| 13.0 | QB 2013+ | Most modern features |
| 14.0 – 16.0 | QB 2014–2016 | Minor additions |
| 17.0 | QB 2017+ | Latest, recommended |

**Our target: qbXML 13.0** — compatible with all QB versions from 2013 onward. The service will negotiate down based on `qbXMLMajorVers`/`qbXMLMinorVers` reported in `sendRequestXML`.
