<!-- Set 1 queue position i150 -->
From the billing office lead: the last day to file a claim

Payers deny claims that arrive after their filing limit, so before a claim goes out we need to know how long we have. When someone asks for the filing deadline of a claim we haven't sent yet, they'll give you the patient and the date of service. Today is 2026-10-14.

## Which claim they mean

It's the claim with that date of service on the patient's list of claims not yet filed, which you'll find with the insurance information in the chart. The patient will often also have a claim with the same date of service in the Claims area. Everything in the Claims area has already gone to a payer, so it is never the claim being asked about, and nothing on it is used.

Each claim on the not-yet-filed list has a type (Original, Secondary, or Corrected) and the payer it is billed to. A Secondary claim also shows the date the primary payer's remittance arrived, or that it hasn't been received. A Corrected claim shows the date the remittance for the original claim arrived.

## Which filing terms to use

Use the claim filing terms of the payer the claim is billed to. The terms give a limit for an Original claim (in days or in months), one for a Secondary claim (in days), one for a Corrected claim (in days), and the date they took effect. When a payer has more than one set, use the set in effect on the date of service, meaning the one with the latest effective date on or before it. The set in effect today or on a remittance date doesn't matter.

The Claims area also shows, with each payer's contract terms, a number of days within which the payer accepts claims. That is a different figure. Don't use it for this.

Check this first: if the payer had no claim filing terms in effect on the date of service, the answer is `NO_FILING_TERMS`, whatever the type of claim. That includes a Secondary claim still waiting on the primary payer.

## Counting to the last day

| Type | Counted from | Limit |
|---|---|---|
| Original | The date of service | The limit for an Original claim |
| Secondary | The date the primary payer's remittance arrived | The limit for a Secondary claim |
| Corrected | The date the remittance for the original claim arrived | The limit for a Corrected claim |

A Secondary claim whose primary remittance hasn't been received can't go out yet. The answer for it is `AWAITING_PRIMARY`.

For a limit in days, add that many days to the starting date: 90 days from 2026-01-10 is 2026-04-10.

For a limit in months, go to the same day of the month that many months later: 12 months from 2025-11-03 is 2026-11-03. If that month doesn't have that day, use its last day, so 6 months from 2025-08-31 is 2026-02-28.

## Weekends and office holidays

We only file on days the billing office is open. It's closed Saturdays, Sundays, and these holidays: 2025-11-27 (Thanksgiving), 2025-11-28 (Day after Thanksgiving), 2025-12-25 (Christmas Day), 2026-01-01 (New Year's Day), 2026-05-25 (Memorial Day), 2026-07-03 (Independence Day, observed), 2026-09-07 (Labor Day), 2026-11-26 (Thanksgiving), 2026-11-27 (Day after Thanksgiving), 2026-12-24 (Christmas Eve), 2026-12-25 (Christmas Day), 2027-01-01 (New Year's Day), 2027-05-31 (Memorial Day), 2027-07-05 (Independence Day, observed), 2027-09-06 (Labor Day), 2027-11-25 (Thanksgiving), 2027-11-26 (Day after Thanksgiving), 2027-12-24 (Christmas Eve). Use this list, not the clinic calendar. The clinic calendar has the closures of the clinic locations, which aren't the same.

If the day you counted to falls on a day the office is closed, the last day to file is the nearest earlier day it's open. It never moves later.

## How to answer

- If the last day is today or later, give the date as `YYYY-MM-DD`, for example `2026-11-20`.
- If the last day has passed, give `EXPIRED:<days>`, the number of days from the last day to today. A last day of 2026-10-09 checked on 2026-10-14 is `EXPIRED:5`.
- Otherwise `NO_FILING_TERMS` or `AWAITING_PRIMARY`, as above.

## Example

Request: "Davis, Andrea, DOB 2018-12-19, date of service 2026-05-07. We haven't billed this one yet. What's the deadline to file?"

Answer: `2027-05-07`

Under Claims not yet filed in the chart's Insurance section, claim 87827990 is an Original claim for a visit on 2026-05-07, billed to Union Workers Health Fund. In the Claim filing table on the Union Workers Health Fund page in the Payers area, the row in effect on that date is the one effective 2024-01-01. The limit for this claim type is counted from the date of service, 2026-05-07, and 365 days from then is 2027-05-07. The office is open that day, so that is the deadline. Today is 2026-10-14, so the deadline has not passed.
