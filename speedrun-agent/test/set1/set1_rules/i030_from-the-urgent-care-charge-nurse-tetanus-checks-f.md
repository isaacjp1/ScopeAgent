<!-- Set 1 queue position i030 -->
From the urgent care charge nurse: tetanus checks for wound visits

For every wound we see, the patient needs a tetanus vaccine, a tetanus vaccine plus tetanus immune globulin (TIG), or neither. We go by the CDC wound management table, applied the way it's written here. You'll be asked what a patient should have had at a wound visit, with the patient and the date of the visit. The answer is what they should have had, whatever was actually given.

## How to answer

`<ACTION>:<count>:<last>`, where:

- `ACTION` is `VACCINE`, `VACCINE_AND_TIG`, or `NONE`.
- `count` is the number of documented tetanus doses the patient had before the day of the visit.
- `last` is the date of the most recent of those doses as YYYY-MM-DD, or `NONE` if the count is 0.

For example: `VACCINE:2:2019-05-03`, `NONE:5:2021-08-14`, `VACCINE_AND_TIG:0:NONE`.

## Was there a wound visit?

Every wound visit has a triage note written that day whose text starts with `Triage:`. If the chart has no such note on that date, there was no wound visit, and the answer is `NO_WOUND_VISIT`. Only the triage note decides this: an appointment, a visit, or a vaccine entry on that date doesn't make it a wound visit, and neither does a phone call note that mentions a triage nurse.

## The decision

| Documented tetanus doses before the visit | Clean and minor wound | Any other wound |
|---|---|---|
| 0, 1, or 2 | `VACCINE` | `VACCINE_AND_TIG` |
| 3 or more | `VACCINE` if the last dose was 10 or more years before the visit, otherwise `NONE` | `VACCINE` if the last dose was 5 or more years before the visit, otherwise `NONE` |

For the years, count back to the same month and day that many years before the visit. A last dose on that date or earlier is that many years old. For a visit on 2026-05-10, a last dose on 2016-05-10 is 10 years old and one on 2016-05-11 is not. A last dose on 2021-05-10 is 5 years old and one on 2021-05-11 is not. If the visit is on February 29, count back to March 1 of the earlier year.

## Clean and minor, or any other wound

Go by the triage note. The wound is clean and minor unless the note says the wound treated at this visit is:

- Contaminated with dirt, soil, feces, or saliva. A bite, from an animal or a person, has saliva in it.
- A puncture wound.
- An avulsion, where skin is torn away.
- A missile wound: a bullet, a pellet, or shrapnel.
- A crush injury.
- A burn.
- Frostbite.

When one of these applies, the note says so in plain words, and nothing else makes it "any other wound". A cut from a knife, glass, paper, or a razor, or a scrape, with nothing in it, is clean and minor however long or deep it is. A sentence that rules something out, such as "No dirt, soil, or saliva in the wound" or "Not a puncture and not a bite", describes a clean wound. Ignore what the note says about someone else's wound, or about an earlier wound of the patient's that has healed.

## Counting documented tetanus doses

A documented dose is a record that a tetanus vaccine was given on a stated date. Use records from every location in the group. Three kinds count, and nothing else in the chart does:

1. **Immunization entries in the chart.** Every entry counts except one marked "Entered in error", whether it says the dose was given at one of our locations or "Given elsewhere, from the patient's records".
2. **Outside immunization records**: documents printed by another clinic or a health department, usually scanned, filed with the type "Immunization record". Their titles start with "Immunization record:" and the name of the place that printed them. Every date printed for a tetanus vaccine is a dose. A document of any other type, such as a discharge summary or a referral letter, is not a record of a dose.
3. **Our own notes of a tetanus vaccine given here** at a visit, with its lot number. For example: "Td (Tenivac) given today in the left deltoid, lot number TK4471D." The dose date is the date of the note.

Some patients have a second chart that was opened by mistake and later merged into the main one. Whatever was filed under the duplicate (immunization entries, notes, documents) shows in the main chart with nothing to set it apart, and counts like the rest.

These are not documented doses:

- What the patient says about past shots, such as "thinks the last tetanus shot was about 6 years ago" or "says the tetanus shots are up to date".
- A note that a vaccine was offered, discussed, declined, or ordered but not given, or that a letter about a vaccine lot was mailed.
- A note about a vaccine that another clinic or a pharmacy gave.

When you count:

- Count only doses given before the visit date. A dose given on the day of the visit (usually the shot for this wound) does not count, and neither does anything given later.
- All records of a tetanus vaccine with the same date are one dose. The same dose often appears more than once: in the chart and on an outside record, on an outside record filed twice, repeated on a merged record, in a note and a chart entry for the same visit, or under two different names.
- Count every documented dose, whatever the patient's age at the time and however close together the doses were.

### Dates on outside records

Near the top of each outside record, under Sex, "Dates written" says how it writes dates: `YYYY-MM-DD`, `MM/DD/YYYY`, `DD.MM.YYYY`, or day month year (as in `14 Mar 2021`).

Some records list one dose per row. Others are a grid, with a row for each vaccine and its doses side by side under Dose 1, Dose 2, and so on. In a grid, later dates in a row can be printed without the year (`05/16`, `16.05.`, `16 May`). Such a date is the first date with that month and day after the date before it in the same row. A row reading `03/14/2019`, `05/16`, `11/02`, `01/15` means 2019-03-14, 2019-05-16, 2019-11-02, and 2020-01-15.

### Which vaccines are tetanus vaccines

A record is of a tetanus vaccine if it names one of these. The first column is the name the chart's entries use, the second is the name an outside record prints.

| Name in the chart | Name on an outside record |
|---|---|
| DTaP (Daptacel) | Daptacel |
| DTaP (Infanrix) | Infanrix |
| DTaP-HepB-IPV (Pediarix) | Pediarix |
| DTaP-IPV/Hib (Pentacel) | Pentacel |
| DTaP-IPV-Hib-HepB (Vaxelis) | Vaxelis |
| DTaP-IPV (Kinrix) | Kinrix |
| Tdap (Boostrix) | Boostrix |
| Tdap (Adacel) | Adacel |
| Td (Tenivac) | Tenivac |
| DTaP | DTaP |
| Tdap | Tdap |
| Td | Td |

No other vaccine is a tetanus vaccine. That includes Hib (ActHIB), Hib (PedvaxHIB), IPV (IPOL), HepB (Engerix-B), PCV20 (Prevnar 20), MMR (M-M-R II), Varicella (Varivax), Influenza (Fluzone), Influenza (Flucelvax), Zoster (Shingrix), HPV (Gardasil 9), MenACWY (Menveo), and the same vaccines written without a brand name.

## Example

Request: "Doing chart review on wound visits. Kathryn Lewis, DOB 1998-12-03, came in on 2025-02-08. What was due for tetanus?"

Answer: `VACCINE:4:2013-01-14`

In the chart's Notes section, the triage note on 2025-02-08 says the wound is contaminated with feces. That is on the list, so it counts as any other wound. From the Immunizations section, the outside immunization records in Documents, and the notes of vaccines given here, the documented tetanus doses before the visit date, one per date, are 1999-02-24, 1999-04-24, 1999-06-13, 2013-01-14. That is 4. Not counted: a dose given on the visit date. Going back 5 years from the visit date gives 2020-02-08. The last dose, 2013-01-14, is on or before that date, so it is 5 or more years old: VACCINE. The answer is VACCINE:4:2013-01-14.
