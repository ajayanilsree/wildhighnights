# WHN booking accounting update

Implementation and verification: 27 October 2026. Changes are local and uncommitted. No deployment or application-database migration was performed.

## A. Root cause and architecture

The previous `booking_financials` function calculated the artist/WHN split from the entire deal, then subtracted each party's expenses from that party's share. This neither calculated commission on the expense-adjusted base nor included reimbursements in payouts. The ledger called WHN's share minus WHN expenses “WHN Net Profit”.

Artist expenses already exist in `BookingExpense.amount`, classified by `borne_by='Artist'`; WHN expenses use `borne_by='WHN'`. These existing rows are reused. An empty category totals INR 0.00. No duplicate expense columns or parallel accounting system were introduced.

Existing artist commission fields actually store **artist share percentages**. A read-only inspection of the local SQLite database confirmed DJ Paroma has Sale 85%, Lead 90%, and Esani has 20%, 15%. The user explicitly chose to preserve that convention and separately correct Esani to 80%, 85%, corresponding to WHN Sale 20%, Lead 15%. Production settings were not queried or changed.

Derived shares/payouts were not stored in database columns. No settlement, invoice, or payment models, tables, or financial export implementation were found in this project. Booking status, booking relationships, expenses, and activity logs remain in the existing architecture. Public booking APIs continue to expose event information only; financial calendar data remains authenticated and role scoped.

## B. Files changed

Paths below are relative to this report's directory (`whn-bookings`).

| File | Change |
|---|---|
| `bookings/financials.py` | Central Decimal calculation, validation, expense aggregation, artist-rate selection, historical-rate provenance, and POST financial-input validation. |
| `bookings/models.py` | Booking rate snapshot and percentage/amount validators; model/admin aggregate-expense validation. |
| `bookings/views.py` | Shared calculation for accounts, summaries, calendars, and linked CRM conversions; exact decimal strings in financial payloads; atomic booking writes; validate before mutation; booking and artist-setting authorization checks. |
| `bookings/migrations/0031_booking_applied_artist_percentage_and_more.py` | Nullable rate snapshot plus field validators. |
| `bookings/migrations/0032_correct_esani_artist_shares.py` | User-approved, conditional Esani setting correction. |
| `bookings/tests.py` | Update original assertions for revised accounting and approved Esani settings; retain regression coverage. |
| `bookings/test_financials.py` | Financial examples, boundary/rounding tests, creation/editing, transaction rollback, permissions, reports/APIs, historical handling, and migration preservation tests. |
| `bookings/test_browser.py` | Opt-in Chromium workflow with disposable database, validation recovery, desktop and mobile checks. |
| `whn_bookings_dj/test_settings.py` | Isolated in-memory SQLite, media storage, and static-file test configuration. Overrides the application's configured database. |
| `templates/bookings/add_booking.html` | Expense-category labels/help, nonnegative amounts, visible errors, and submitted-value restoration. |
| `templates/bookings/edit_booking.html` | Equivalent expense/category/error/validation updates for editing. |
| `templates/bookings/booking_form_restore.html` | Safely restore submitted form values and expense rows after server validation errors using escaped JSON. |
| `templates/bookings/admin_whn_accounts.html` | Separate expense categories and payouts, commission/reimbursement summaries, historical estimate markers, responsive scrolling and unbroken monetary values. |
| `templates/bookings/admin_accounts.html` | Artist payout/reimbursement terminology and historical estimate markers. |
| `templates/bookings/artist_earnings.html` | Equivalent artist-facing summary/ledger updates. |
| `templates/bookings/artist_accounts.html` | Artist payout terminology and historical estimate markers. |
| `templates/bookings/artist_calendar.html` | Artist payout terminology and historical-rate provenance. |
| `templates/bookings/admin_accounts_selection.html` | Describe WHN accounts as payouts rather than profit. |
| `templates/bookings/add_artist.html` | Explicit Artist Share percentage labels and visible errors. |
| `templates/bookings/edit_artist.html` | Equivalent labels/errors for editing artist settings. |
| `qa-screenshots/booking-ledger-desktop.png` | Browser evidence from isolated Goa fixture. |
| `qa-screenshots/booking-ledger-mobile.png` | Mobile evidence with the ledger scrolled to payout/date columns. |
| `ACCOUNTING_UPDATE_REPORT.md` | This implementation, validation, and deployment report. |

No runtime dependencies, production environment settings, unrelated credential files, or deployment configuration were changed. Test-generated changes to tracked Python bytecode were restored.

## C. Database changes and historical records

Migration 0031 adds `Booking.applied_artist_percentage`, a nullable two-decimal percentage. New bookings snapshot the selected artist's applicable artist share. Editing expenses, amount, status, notes, or the artist's current settings does not change that retained rate. Explicitly changing the booking's artist, booking type, or Custom percentage selects and records the newly applicable rate.

Existing bookings remain NULL: the migration does not pretend to know their originally agreed rates. Existing Custom bookings already carry a reliable booking-level percentage and use it. Other legacy bookings calculate **provisional estimates** using current artist settings and show “Estimate: historical rate unrecorded”. Affected account summaries also show that totals are provisional. Merely viewing or editing expenses does not backfill an unknown historical rate.

Migration 0032 changes Esani only when both old settings are still exactly 20%/15%. It updates them together to 80%/85%; independently edited settings are left untouched. It is idempotent. Its reverse is intentionally a no-op so rolling code back does not restore the mistaken business configuration. Neither migration rewrites booking amounts, expense amounts, payment status, activity logs, or applied historical rates.

No application SQLite or production database was migrated. Migrations ran only against disposable test databases. The read-only local check found no bookings whose combined expense total exceeded the deal, and no settlement/invoice/payment tables.

## D. Implemented formulas and rounding

```text
WHN commission percentage = 100 - applicable stored artist percentage
Total Expenses = WHN Expenses + Artist Expenses
Commission Base = Deal Amount - Total Expenses
WHN Share = round_half_up(Commission Base × WHN commission percentage / 100, 2)
Artist Share = Commission Base - rounded WHN Share
Artist Net Payout = Artist Share + Artist Expenses
WHN Net Payout = WHN Share + WHN Expenses
Artist Net Payout + WHN Net Payout = Deal Amount
```

All accounting arithmetic uses Decimal. The artist share is the remainder after rounding WHN commission, ensuring exact reconciliation to the paise. Inputs accept up to two decimal places, including decimal percentages. Nonfinite values, negatives, percentages outside 0–100, malformed expense rows, and combined expenses exceeding the deal are rejected before any booking/expense mutation. Currency displays retain the project's INR symbol and two-decimal convention. Calendar clients format server-provided amounts; they do not recalculate commission.

WHN reimbursement is included only in WHN payout, never added to WHN commission. Artist reimbursements are included only in artist payout. No genuine profit-reporting implementation was found to replace.

## E. Financial results: expected versus actual

All amounts are INR. Each cell shows **expected = actual** from executed assertions.

| Case | WHN Share | Artist Share | Artist Net Payout | WHN Net Payout |
|---|---:|---:|---:|---:|
| 160,000 deal; WHN 20,000; artist 10,000; WHN 10% | 13,000.00 = 13,000.00 | 117,000.00 = 117,000.00 | 127,000.00 = 127,000.00 | 33,000.00 = 33,000.00 |
| Goa: 80,000; WHN 15,909; artist 0; WHN 10% | 6,409.10 = 6,409.10 | 57,681.90 = 57,681.90 | 57,681.90 = 57,681.90 | 22,318.10 = 22,318.10 |
| Esani Sale: 100,000; WHN 5,000; artist 5,000; WHN 20% | 18,000.00 = 18,000.00 | 72,000.00 = 72,000.00 | 77,000.00 = 77,000.00 | 23,000.00 = 23,000.00 |
| Esani Lead: same expenses; WHN 15% | 13,500.00 = 13,500.00 | 76,500.00 = 76,500.00 | 81,500.00 = 81,500.00 | 18,500.00 = 18,500.00 |
| No expenses: 100,000; WHN 10% | 10,000.00 = 10,000.00 | 90,000.00 = 90,000.00 | 90,000.00 = 90,000.00 | 10,000.00 = 10,000.00 |
| WHN expenses only: 100,000; WHN 10,000; WHN 10% | 9,000.00 = 9,000.00 | 81,000.00 = 81,000.00 | 81,000.00 = 81,000.00 | 19,000.00 = 19,000.00 |
| Artist expenses only: 100,000; artist 10,000; WHN 10% | 9,000.00 = 9,000.00 | 81,000.00 = 81,000.00 | 91,000.00 = 91,000.00 | 9,000.00 = 9,000.00 |
| Expenses equal deal: 100,000; WHN 60,000; artist 40,000 | 0.00 = 0.00 | 0.00 = 0.00 | 40,000.00 = 40,000.00 | 60,000.00 = 60,000.00 |

Each valid case also asserts exact payout reconciliation. Additional executed checks cover zero deal, 0% and 100% commission, 12.35% commission, half-paise rounding (0.10 × 15% → WHN 0.02, artist 0.08), and 707 cent/rate combinations. The excess-expense example 100,000 / 80,000 / 30,000 is rejected with the requested error. Negative, NaN, infinity, excessive precision, and invalid/custom percentages are rejected.

## F. Automated and browser verification

Final full suite: **53 passed, 0 failed, 0 skipped**, Django **5.1.7** (the project's pinned version), Python 3.12, isolated SQLite. The complete final suite ran in approximately 30 seconds. Earlier exploratory runs exposed obsolete financial assertions and a Playwright/Django test-loop compatibility issue; these were corrected before the successful final suite.

Coverage includes the existing CRM/calendar/accounts regressions, the client financial examples, independent artist rates, legacy defaults, Custom bookings, rate retention, input validation, atomic rollback, authorized employee editing, denied unauthorized editing, authenticated calendar payloads, read-only public booking behavior, account totals, filtering/date ordering, and schema/data preservation. The migration test also verifies the Esani correction is idempotent and preserves independently changed settings.

The real Chromium test uses Django's disposable live server. It creates an artist through the UI, configures Sale/Lead shares, creates and edits expenses, saves and reloads, checks ledger values, reproduces the Goa case without touching its production record, checks visible server validation errors and form-value recovery, and verifies horizontal table scrolling at a 390px viewport without page overflow. Desktop and mobile screenshots were visually inspected. Existing ledger pagination does not exist, so none was added or claimed tested.

Additional checks executed successfully:

```text
manage.py makemigrations --check --dry-run --settings=whn_bookings_dj.test_settings
manage.py check --settings=whn_bookings_dj.test_settings
git diff --check
```

To reproduce from `whn-bookings`, with the project's virtual environment active:

```powershell
# Backend suite; the browser test is explicitly skipped unless opted in.
python manage.py test bookings --settings=whn_bookings_dj.test_settings --noinput

# Full suite when Playwright and Chromium are available in the test environment.
$env:WHN_BROWSER_TESTS = '1'
python manage.py test bookings --settings=whn_bookings_dj.test_settings --noinput
```

Playwright is an optional test dependency, not an added production requirement. In this workspace it was already installed in the system Python environment. The final verification used the project virtual environment's pinned Django and appended the existing system package directory for browser-test dependencies only. Browser process access required execution outside the restricted process environment; tests still used only the isolated local application database.

## G. Deployment notes

Deployment and production migrations require separate authorization. No backup of production was taken because no production data was modified or connected to during this task.

1. Confirm the target database and inspect `showmigrations bookings`. The new migrations depend on existing migration 0030; do not edit or replay existing migrations blindly.
2. Back up production and verify restoration before applying schema/configuration changes.
3. Restore a copy into isolated staging. Review Esani's current settings and run the migrations there. Confirm booked/finalized accounts against independent settlement records, especially legacy bookings marked as estimates.
4. Run the tests above and verify representative real staging bookings, including the Goa record and artist-specific rates. SQLite migration tests do not establish PostgreSQL production compatibility; that staging rehearsal is still required.
5. After explicit approval, apply `python manage.py migrate` against the intended target with the matching code release. No new application environment variables are required.
6. Recheck WHN commission, both expense categories, both payouts, record counts, and agreed historical rates. Obtain reliable rates from agreements/settlements before recording any historical rate correction. No automatic backfill is provided.

The existing Render `build.sh` runs `python manage.py migrate` automatically. Deploying this branch would therefore apply both new migrations; review and authorization must happen before triggering that build. The build configuration was not changed or executed.

## H. Remaining limitations and assumptions

- Production deployment, PostgreSQL migration rehearsal, production backups, and comparison with external finalized settlements remain outstanding deployment work. No production changes are claimed.
- Legacy Sale/Lead bookings have no reliable original-rate snapshot; their live figures are explicitly provisional. Current artist-setting changes may change those estimates. Saved new bookings retain their agreed rates.
- Esani's correction is prepared in migration 0032 and verified in test databases; the existing application database still has its original values until an authorized migration.
- There are no implemented accounting exports, settlement/payment models, or ledger pagination in this repository to update or regression-test. External financial integrations, if any, require separate verification. Financial calendar amounts now use exact decimal strings; external consumers expecting numeric JSON types should account for this.
- Model validators and form/service validation protect the application and Django admin workflows. Raw SQL, `QuerySet.update`, and bulk ORM operations bypass normal model validation and booking-rate snapshot behavior; any separate import tooling must call the shared service and explicitly handle historical rates.
- Existing form/file workflows are retained. Browsers cannot restore selected file uploads after a server validation response; users must reselect files when resubmitting such a form.
