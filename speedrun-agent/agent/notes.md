## Wrenfield guide (learned from the practice clinic; this clinic's version may differ, trust what the pages show)

- Every page is reached by URL. Paths and query parameters seen in practice:
  - Patients search: `/patients?lastName=Driscoll` or `/patients?dob=YYYY-MM-DD`. Results list "Last, First", MRN, DOB (MM/DD/YYYY) and sex, and link to `/patients/<id>`.
  - Patient chart `/patients/<id>` has tabs (Billing, Invoices, Demographics, Insurance, Problems, Notes, Documents, Appointments, Activity). Use the tab links shown on the chart page, e.g. `/patients/<id>/appointments`, `/patients/<id>/documents`.
  - Schedule: `/schedule?date=YYYY-MM-DD` (day view), `/schedule/providers/<id>?date=...`, `/schedule/appointments?from=YYYY-MM-DD&to=YYYY-MM-DD&location=...&status=...` (list). Status codes in practice: 1 Scheduled, 2 Completed, 3 Cancelled, 4 Late cancel, 5 No-show.
  - One provider's appointments on a day, every location: `/schedule/appointments?from=YYYY-MM-DD&to=YYYY-MM-DD&provider=<provider id>&status=1` (leave `location` out for all locations; drop `status` to see every status). provider_info gives the provider id.
  - Billing: `/billing` with GET filters `number, patient, location, status (open|partial|paid|void), serviceFrom, serviceTo, issuedFrom, issuedTo, owedAtLeast, owedAtMost, sort`. An invoice by number: `/billing?number=<number>`, then its link `/billing/invoices/<id>`. The invoice page has Total, Status and a Ledger (Charges | Payments and adjustments) ending in "Amount owed". A patient's invoices: `/billing/accounts/<patient id>`.
  - Documents: `/documents?kind=lab_report|referral_letter|statement&patient=<name>&from=&to=`.
  - Activity log: `/activity` (what staff did, filter by user).
- The agent is set to "All locations", so patient search covers every location. Lists elsewhere may still have their own location filter.
- Several patients can share a last name: match first name AND date of birth when the task gives them. Accents may differ (Martinez vs Martínez); search without accents if nothing is found.
- Times are shown in the location's time zone (Kansas sites Central, Colorado sites Mountain).
- Some charts are restricted ("This chart is restricted ... Give a reason to open it"). The agent does not request access to restricted charts.
- Long lists (patient search, charts, recurring dates) are paged by the server; the agent clicks through every page for you and says WARNING if a list could not be read in full.
- Documents open in a viewer: read_document returns the text of the document's PDF.
- Merged duplicates: the duplicate's link opens the surviving chart with a banner "The record with MRN ... was merged into this record"; the surviving chart shows what was filed under the duplicate.
- Recurring appointments are listed on the Appointments tab as series (link to /patients/<id>/recurring/<id>); each series page lists every date with that date's status (moved dates say "moved from ...").
- Provider pages show the specialty under the name ("Family Medicine · Thursday, ..."); providers who left are in the Inactive group of the provider list.
