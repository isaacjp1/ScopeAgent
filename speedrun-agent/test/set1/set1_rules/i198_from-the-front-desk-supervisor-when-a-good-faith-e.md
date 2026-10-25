<!-- Set 1 queue position i198 -->
From the front desk supervisor: when a good faith estimate is due

When a patient isn't using insurance for a scheduled visit, we have to give them a good faith estimate of the charges (No Surprises Act, 45 CFR 149.610). How soon it's due depends on how far ahead the visit was scheduled. Here's the rule, so you can answer when the front desk asks about an appointment. The numbers are as of October 1, 2026.

You'll get the patient and the date and start time of one appointment. The time is on a 24-hour clock in the local time of the appointment's location, so 14:40 is 2:40 PM. It's always a single appointment, never one date of a recurring appointment, and it can be at any of our locations.

## Is insurance paying for the visit?

We owe an estimate when insurance isn't paying, which means either of these:

- The chart has no insurance on file. For this, the insurance the chart itself is registered with (payer, plan, and member ID) decides, and nothing else does. If the chart says no insurance is on file, the patient counts as uninsured for the estimate, even if the chart lists coverage records, authorizations, or claims.
- The chart has insurance on file, but a note in the chart says the patient chose to pay for this visit themselves and insurance isn't to be billed for it. The note has to name the date of this appointment. Any type of note counts (chart note, phone call, or message), whenever it was written.

Otherwise the answer is `NOT_REQUIRED:INSURED` and nothing below applies.

Some notes about paying look similar but don't make the visit self-pay:

- The patient asked about the self-pay price and then decided to use insurance.
- The patient won't self-pay.
- The self-pay is for someone else, such as a family member with their own visit.
- The note names a different date.
- The patient used to be self-pay and insurance is billed now.

## The scheduling date

The scheduling date is the date the appointment was booked. If the start time was moved after booking, it's the date of the most recent move instead. Other changes to the appointment, such as a change of status, don't change the scheduling date. Take these dates in the local time of the appointment's location.

## Business days

A business day is a Monday through Friday when the appointment's location isn't closed. The location is closed on a date when the clinic calendar has an entry for that date with the status Active that applies to all locations or to this one. Entries with the status Withdrawn and closures of other locations don't count.

## The deadline

Count the business days after the scheduling date, up to and including the appointment date. Don't count the scheduling date itself. Count the appointment date if it's a business day.

- 0 to 2 business days: `NOT_REQUIRED:SHORT_NOTICE`.
- 3 to 9 business days: the estimate is due on the first business day after the scheduling date.
- 10 or more business days: it's due on the third business day after the scheduling date.

Booked Monday 2026-03-02 for Thursday 2026-03-05 with no closures: Tuesday, Wednesday, and Thursday make 3 business days, so the estimate is due Tuesday 2026-03-03. If Tuesday 2026-03-03 is an Active closure for that location, only Wednesday and Thursday count, and the answer is `NOT_REQUIRED:SHORT_NOTICE`. Booked Friday 2026-03-06 for Friday 2026-03-20 with no closures: that's 10 business days, so the estimate is due on the third business day after March 6, which is Wednesday 2026-03-11.

The appointment's status (Scheduled, Completed, Cancelled, or anything else) doesn't change the answer, and a due date that has already passed is still the answer.

## How to answer

Give the date the estimate is due as `YYYY-MM-DD`, or `NOT_REQUIRED:INSURED` or `NOT_REQUIRED:SHORT_NOTICE`.

## Example

Request: "Good faith estimate question: Williams, Ann, born 1934-10-19, 11:00 on 2025-04-04. Is one required, and if so, when's it due?"

Answer: `2025-03-19`

The chart's Insurance section says No insurance on file, so we owe an estimate. The appointment's Booking panel shows it was booked on 2025-03-14, and its History has no Start time moved entry, so 2025-03-14 is the scheduling date. From the next day through 2025-04-04, the location has 15 business days, counting Monday through Friday and leaving out the Active closures on the clinic calendar that apply to it. That is 10 or more, so the estimate is due on the third business day after the scheduling date, 2025-03-19.
