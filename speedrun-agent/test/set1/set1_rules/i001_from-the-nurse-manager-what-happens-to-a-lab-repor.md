<!-- Set 1 queue position i001 -->
From the nurse manager: what happens to a lab report when it comes in

When you're asked what to do with a lab report, decide it with the steps below. The choices are to call the provider right away, to have a nurse review it, or to release it to the patient. Go by our own limits in the table at the end, not by the reference range or the high and low flags the lab prints on the report.

A request names the patient, the panel, and the date the report was received into the chart. A report that was filed twice is in the chart twice, and each copy has its own received date.

## Panels this rule covers

Complete blood count, Basic metabolic panel, Thyroid panel. For a report of any other panel, answer `NOT_COVERED`.

## Critical results

A result is critical when it is below the low critical limit or above the high critical limit for that test. A result exactly at a limit is not critical.

If anything on the report is critical, answer `CALL_PROVIDER_NOW:` followed by the name of every critical test as the report prints it, in alphabetical order, separated by commas, for example `CALL_PROVIDER_NOW:Potassium,Sodium`. Nothing else on the report matters then.

## Review items

If nothing is critical, count the review items. A test is one review item if it is out of range, fails the change rule, or both. One or more review items is `NURSE_REVIEW:<n>`, for example `NURSE_REVIEW:2`. None is `RELEASE`.

**Out of range** means below the low end or above the high end of the review range. A result exactly on an end is in range. Some ranges depend on the patient:

- Sex is the sex on the chart. If it is neither Female nor Male, a result is in range when it is inside either the female range or the male range.
- Age is the patient's age in whole years on the date the sample was collected, as printed on the report. A patient born on February 29 turns a year older on March 1 in years without a February 29.
- Type 2 diabetes mellitus counts when it is on the problem list, whatever its onset date.

**The change rule** applies only to the tests that have one in the table. Compare the result with the same test on the previous report. The change is the difference between the two, as a percentage of the previous result. More than the table's percentage is a review item, even when the result is in range. Exactly the percentage is not. For Hemoglobin (more than 15%) with a previous result of 12.0, a result of 13.8 is a change of exactly 15% and is not a review item. A result of 13.9 is.

## The previous report

- Use only reports that print this chart's record number. A report in the chart that prints a different record number is ignored, both as the report asked about and as a previous report.
- Each report prints a report number. Two copies in the chart with the same report number are the same report filed twice. The second copy is not a previous report.
- The previous report is the other report of the same panel with the latest collected date before this report's collected date. If two have that date, take the one with the higher report number. The received date plays no part in this.
- Use the previous report for the change rule only if it was collected within the 12 months before this report. For a report collected on 2026-05-10, that means collected on 2025-05-10 or later. For a report collected on February 29, the same date a year earlier is February 28. If the previous report is older than that, or there is none, no test fails the change rule.

## Table

Results, ranges, and limits are in the units the report prints.

**Complete blood count**

| Test | Unit | Review range | Critical when | Change rule |
|---|---|---|---|---|
| White blood cell count | 10^3/uL | 4.0 to 11.0 | below 2.0 or above 30.0 | none |
| Hemoglobin | g/dL | Female: 12.0 to 15.5. Male: 13.5 to 17.5 | below 7.0 or above 20.0 | more than 15% |
| Hematocrit | % | Female: 36.0 to 46.0. Male: 41.0 to 53.0 | below 21.0 or above 60.0 | none |
| Platelet count | 10^3/uL | 150 to 400 | below 50 or above 1000 | more than 30% |

**Basic metabolic panel**

| Test | Unit | Review range | Critical when | Change rule |
|---|---|---|---|---|
| Sodium | mmol/L | 135 to 145 | below 120 or above 160 | none |
| Potassium | mmol/L | 3.5 to 5.1 | below 2.8 or above 6.2 | none |
| Chloride | mmol/L | 98 to 107 | none | none |
| Carbon dioxide | mmol/L | 22 to 29 | below 10 or above 40 | none |
| Blood urea nitrogen | mg/dL | Age under 65: 7 to 20. Age 65 or over: 8 to 26 | above 100 | none |
| Creatinine | mg/dL | Female: 0.50 to 1.10. Male: 0.70 to 1.30 | above 5.00 | more than 25% |
| Glucose | mg/dL | 70 to 99. With Type 2 diabetes mellitus on the problem list: 70 to 180 | below 50 or above 400 | none |
| Calcium | mg/dL | 8.6 to 10.2 | below 6.5 or above 13.0 | none |

**Thyroid panel**

| Test | Unit | Review range | Critical when | Change rule |
|---|---|---|---|---|
| Thyroid stimulating hormone | mIU/L | Age under 65: 0.40 to 4.50. Age 65 or over: 0.40 to 6.00 | none | none |
| Free T4 | ng/dL | 0.80 to 1.80 | none | none |

## Example

If someone asks: "What happens to the Basic metabolic panel lab report for Nancy Oliver (born 2011-04-19), received 2025-11-08?"

The answer is `NURSE_REVIEW:1`.

The report was collected on 2025-11-04. The patient was 14 on that date, and the problem list does not have Type 2 diabetes mellitus. There is no earlier report of this panel, so no test fails the change rule. Sodium 145: in range. Potassium 5.0: in range. Chloride 98: in range. Carbon dioxide 23: in range. Blood urea nitrogen 17: in range. Creatinine 1.17: out of range. Glucose 85: in range. Calcium 9.7: in range.
