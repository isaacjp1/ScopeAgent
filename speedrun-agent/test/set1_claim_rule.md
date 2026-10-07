From the billing supervisor: working a claim after its remittance

When a remittance comes back on a claim, the claim needs a next step. Pick it with the rule below. The request names the patient and the claim's date of service. Today is 2026-10-14.

The answer is one of these:

| Answer | When |
|---|---|
| `AWAIT_PAYER` | The payer has not given a final answer yet |
| `NO_ACTION` | Paid, and the patient owes nothing |
| `BILL_PATIENT:<amount>` | Paid, and the patient owes this amount |
| `BILL_OTHER:<plan>` | Denied because another plan should pay, and we know which one |
| `CONTACT_PATIENT` | Denied because another plan should pay, and we have no plan on record that covered the patient |
| `RESUBMIT:<field>` | Denied for missing information, and the payer said which field |
| `CALL_PAYER` | Denied for missing information, and the payer did not say which field |
| `APPEAL:<last day to appeal>` | Denied, and we have grounds and time to appeal |
| `WRITE_OFF:<amount>` | Denied, and we cannot appeal |

Write amounts in dollars with two decimals and no dollar sign or thousands separator (`45.00`, `1250.50`), and dates as `YYYY-MM-DD`. Examples: `BILL_PATIENT:45.00`, `APPEAL:2026-11-07`, `WRITE_OFF:160.00`.

A claim filed under a duplicate record that was later merged into the patient's chart is the patient's claim like any other. The authorizations filed under both records count for it.

## Start from the current remittance

A remittance is the payer's answer on a claim: what it allowed, paid, and adjusted on each line. A remittance is either a payment or the reversal of an earlier payment. A reversal is the payer taking a payment back.

Work the claim from its current remittance: of the payments on the claim that have not been reversed, the one with the latest payment date. A reversal is never the current remittance. Use only the lines of the current remittance for this claim. One remittance can pay several claims. Earlier remittances play no part, even when they show a different outcome. The lines of a paper remittance that was scanned count the same as keyed lines.

If no remittance has been received for the claim, or every payment on it has been reversed, the payer has not given a final answer: `AWAIT_PAYER`.

## Reading a remittance line

A line has adjustments. An adjustment is a group code, a reason code, and an amount, written like `CO-45 47.60`. A line can have several adjustments and can also carry remark codes.

The group code says who carries the amount. `CO` (contractual obligation) is ours to absorb and can never be billed to the patient. `PR` (patient responsibility) is the patient's.

The reason codes, with their standard X12 meanings:

| Reason | Meaning |
|---|---|
| 1 | Deductible amount. |
| 2 | Coinsurance amount. |
| 3 | Co-payment amount. |
| 16 | Claim/service lacks information or has submission/billing error(s). At least one remark code must be provided. |
| 22 | This care may be covered by another payer per coordination of benefits. |
| 29 | The time limit for filing has expired. |
| 45 | Charge exceeds fee schedule/maximum allowable or contracted/legislated fee arrangement. |
| 97 | The benefit for this service is included in the payment/allowance for another service/procedure that has already been adjudicated. |
| 197 | Precertification/authorization/notification/pre-treatment absent. |

A line is denied when it has an adjustment with group `CO` and reason 16, 22, 29, 97, or 197. `CO-45` is not a denial. It is the normal write-down to the contracted rate on a line that was paid, and it is never part of any amount in this rule.

## Nothing denied

If none of the claim's lines on the current remittance is denied, the claim was paid. Add up the `PR` adjustments with reason 1, 2, or 3 on the claim's lines. If they come to more than zero, bill the patient for that total, however small: `BILL_PATIENT:<total>`. If they come to zero: `NO_ACTION`.

## Something denied

A claim can be denied for more than one reason across its lines. Work it by one reason only, the one that comes first in this order: 29, 22, 16, 197, 97. Leave the denials with the other reasons alone.

The denied amount is the total of the `CO` adjustments with that one reason, across the claim's lines. Denials with other reasons, `CO-45`, and `PR` amounts are not part of it. A write-off is always for the denied amount.

**Reason 29, filed too late.** The payer's contract says how many days after the date of service it accepts claims. The last day to file is the date of service plus that many days: with 90 days, a service on 2026-06-01 had to be filed by 2026-08-30. We can prove timely filing if one of the claim's submissions was accepted by the payer with a result date on or before that last day. A submission the clearinghouse rejected never counts. With proof, appeal (see Appeals). Without it: `WRITE_OFF:<denied amount>`.

**Reason 22, another plan should pay.** Read the account notes on the claim. Only the most recent note that says anything about the patient's other insurance counts. It replaces whatever earlier notes said. If that note names a plan that covered the patient on the date of service, bill that plan: `BILL_OTHER:<plan>`, with the plan name as the note writes it and without the payer's name. A note that says "Silver 3500 from Tallgrass Health Plan" gives `BILL_OTHER:Silver 3500`. Otherwise: `CONTACT_PATIENT`. That covers a claim with no note about other insurance, a note saying the patient has none, a plan that belongs to someone else and does not cover the patient, and a plan that ended before the date of service.

**Reason 16, information missing.** Look at the remark codes on the lines denied with reason 16. Go down this table from the top and stop at the first remark code that appears on any of those lines: `RESUBMIT:<field>`.

| Remark code | Meaning | Field |
|---|---|---|
| N290 | Missing/incomplete/invalid rendering provider primary identifier. | `RENDERING_PROVIDER_ID` |
| N286 | Missing/incomplete/invalid referring provider primary identifier. | `REFERRING_PROVIDER_ID` |
| N382 | Missing/incomplete/invalid patient identifier. | `MEMBER_ID` |
| M51 | Missing/incomplete/invalid procedure code(s). | `PROCEDURE_CODE` |
| M76 | Missing/incomplete/invalid diagnosis or condition. | `DIAGNOSIS` |
| M77 | Missing/incomplete/invalid/inappropriate place of service. | `PLACE_OF_SERVICE` |

Remark code MA130 only says the claim was unprocessable. If none of the codes in the table is on those lines: `CALL_PAYER`.

**Reason 197, no authorization.** An authorization on file for the patient covers a denied line when its payer is the claim's payer, its procedure is the procedure code of the line, and its valid dates include the date of service. The first and last valid days both count. If every line denied with reason 197 is covered, appeal (see Appeals). If even one is not: `WRITE_OFF:<denied amount>`.

**Reason 97, bundled into another service.** The payer may fold the column 2 code of a pair into its payment for the column 1 code:

| Column 1 code | Column 2 code | Indicator |
|---|---|---|
| 17110 | 11102 | 1 |
| 17000 | 11102 | 1 |
| 20610 | 20605 | 1 |
| 12001 | 10060 | 0 |
| 17110 | 11200 | 0 |

A line denied with reason 97 has grounds for appeal only when all three of these are true: its procedure code is the column 2 code of a row with indicator 1, another service line of the same claim as we billed it has that row's column 1 code, and the denied line was billed with modifier 59. Indicator 0 means the two are never paid separately. If every line denied with reason 97 has grounds, appeal (see Appeals). Otherwise: `WRITE_OFF:<denied amount>`.

## Appeals

The payer's contract says how many days it accepts appeals, counted from the payment date of the current remittance. The last day to appeal is that payment date plus that many days: with 120 days, a remittance paid on 2026-07-10 can be appealed through 2026-11-07.

If the last day is today or later, appeal, however small the denied amount: `APPEAL:<last day>`. If the last day has already passed, write the denied amount off: `WRITE_OFF:<denied amount>`.

## Example

If someone asks: "Next step on claim: Coleman, Linda, DOB 1958-09-16, service date 2026-07-06"

The answer is `APPEAL:2026-12-15`.

In the claim page's Remittances panel, the current remittance is CHK4578491, paid on 2026-08-17, with its lines keyed under it. Above it are 2 earlier remittances (a reversed payment and its reversal), which are not used. The claim is denied with reason 197. The denied amount is 190.00. The Authorizations panel has an authorization with the claim's payer for the denied procedure code whose valid dates include the service date, so the denial can be appealed. The payer's contract page gives 120 days under Appeals accepted within, counted from the remittance date, so the last day to appeal is 2026-12-15, which has not passed.
