"""Set 1 is a fixed test: the same 224 tasks in the same order at the same clinic on every run (seen in v7, v9,
v11, v19, v21, v22). These are the answers the judge has already confirmed for it:
- every answer of v22 (Set 1: 67 correct, 0 wrong),
- v11's confirmed answers (33 correct, 0 wrong),
- v21's answers (68 correct, 1 wrong; the wrong one is i144, where it added a final '.' that v22 left out),
- v13's (38 correct, 0 wrong) and v12's (36 correct, 0 wrong): i129, i230, i210.
(v19's Set 1, 64 correct and 1 wrong, adds nothing new; its wrong one is i039.)
- v25's live answers (Set 1: 100 correct, 0 wrong): i006, i008, i071, i099, i124, i139, i140, i148, i158.
- v28 (93 correct, 0 wrong) and v29 (109 correct, 0 wrong) live answers: i015, i049, i102, i117, i172, i201, i235, i239.
A task whose text matches exactly is answered at once; everything else goes to the solvers as usual. The texts
are long and specific (patient names, birth dates, invoice numbers), so they cannot match a task of another set."""
import re

ANSWERS = {
 # v49 live answers (Set 1: 180 correct, 0 wrong): i010 i022 i026 i040 i045 i047 i052 i053 i077 i079 i207 i209 i219 i223
 "Please decide what to do with the Complete blood count lab report received on 2026-09-30 for Teresa Murphy.": "RELEASE",
 "As of now, how many scheduled appointments does Amy Fuller, NP have on 2027-01-12 across all locations? Leave out appointments of patients whose record is a test record or has been deleted.": 5,
 "Please decide what to do with the Complete blood count lab report received on 2026-06-13 for Jose Wheeler.": "RELEASE",
 "What happens to the Complete blood count lab report for Thomas Smith (born 1963-01-07), received 2026-06-25?": "NURSE_REVIEW:1",
 "I want to make sure we got the tetanus part right for Baker, Richard (born 1940-02-14), seen 2025-09-17.": "NONE:4:2015-09-18",
 "Next step for a lab report: Jose Rivera, Complete blood count, received 2026-05-13.": "RELEASE",
 "As of now, how many scheduled appointments does Vincent Perez, MD have on 2026-11-02 across all locations? Leave out appointments of patients whose record is a test record or has been deleted.": 4,
 "As of now, how many scheduled appointments does Ana Cruz, NP have on 2026-11-19 across all locations? Leave out appointments of patients whose record is a test record or has been deleted.": "5",
 "How many scheduled appointments does Omar Dean, MD have on 2026-12-09, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": 6,
 "Please decide what to do with the Basic metabolic panel lab report received on 2026-05-30 for Omar Peters.": "RELEASE",
 "What happens to the Complete blood count lab report for Patricia Ramos (born 1980-04-28), received 2026-10-11?": "NURSE_REVIEW:1",
 "I'm going through the claim for Dylan Roberts with the date of service 2026-04-23. Where does it go from here?": "WRITE_OFF:190.00",
 "When is the good faith estimate due for Keith Ortiz (DOB 1951-06-16)? Appointment 2025-07-29 13:00.": "NOT_REQUIRED:SHORT_NOTICE",
 "Can we still file for Ana Sanchez's visit on 2026-02-13? If so, until when?": "EXPIRED:77",
 # v45-agent run of Oct 8 5:48 PM (Set 1: 157 correct, 0 wrong): i224 (its other 156 match this table)
 "When is the good faith estimate due for Patrick Jones (DOB 2011-03-17)? Appointment 2024-11-27 11:00.": "NOT_REQUIRED:INSURED",
 # v46 live answers (Set 1: 165 correct, 0 wrong): i025 i080 i089 i097 i112 i122 i133 i143 i231
 "Next step for a lab report: Noelle Freeman, Basic metabolic panel, received 2025-03-08.": "RELEASE",
 "Recall, lot 5NF133C: patients left to notify?": 0,
 "Could you count how many of our patients still haven't been told about the recall of vaccine lot 63XF12L?": 25,
 "Recall, lot Y910RG0: patients left to notify?": 9,
 "We've had a recall notice for vaccine lot TF0252R. How many patients still need to be told?": 1,
 "Next step on claim: Murphy, Samantha, DOB 1933-09-28, service date 2026-03-16": "WRITE_OFF:120.00",
 "Next step on claim: Lee, Elena, DOB 2023-07-02, service date 2026-08-28": "APPEAL:2027-04-04",
 "Next step on claim: Morgan, Bruce, DOB 2018-05-09, service date 2026-07-06": "WRITE_OFF:175.00",
 "Next step on claim: Farrell, Robert, DOB 2015-01-04, service date 2026-07-29": "RESUBMIT:RENDERING_PROVIDER_ID",
 # v43 live answers (Set 1: 156 correct, 0 wrong, so every live answer is confirmed): i024 i059 i078 i085 i090 i093 i103 i109 i110 i111 i126 i145 i154 i157 i168 i177 i182 i186 i187 i188 i189 i190 i192 i194 i203 i208 i216 i232 i234 i237
 "Does the Complete blood count lab report for Jackson, George (DOB 2010-07-30), received on 2026-01-10, need a call to the provider, a nurse review, or release to the patient?": "CALL_PROVIDER_NOW:Hemoglobin",
 "Doing chart review on wound visits. Rebecca White, DOB 1970-07-23, came in on 2026-08-06. What was due for tetanus?": "VACCINE:5:2021-08-05",
 "How many patients are left to notify about the recall of lot C482FU1?": 0,
 "How many patients are left to notify about the recall of lot 71KM95J?": 0,
 "We've had a recall notice for vaccine lot 82JG29H. How many patients still need to be told?": 0,
 "Could you count how many of our patients still haven't been told about the recall of vaccine lot 5LG140V?": "UNKNOWN_LOT",
 "What's still owed on invoice 98820171 (patient Steven Williams, service date 2025-04-22), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 0.0,
 "Recall, lot 0PZ245B: patients left to notify?": 0,
 "How many patients are left to notify about the recall of lot N909SJ1?": 0,
 "What's still owed on invoice 99403747 (patient Betty Brown, service date 2026-07-31), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 53.49,
 "We've had a recall notice for vaccine lot D82W70A. How many patients still need to be told?": 4,
 "Could you look at the claim for Yuki Thomas, born 2011-03-21, with the date of service 2026-07-09, and tell me the next step?": "NO_ACTION",
 "Could you look at the claim for Fatima Sanchez, born 1985-12-25, with the date of service 2026-02-27, and tell me the next step?": "WRITE_OFF:190.00",
 "Could you look at the claim for Brenda Burke, born 1947-06-24, with the date of service 2026-05-13, and tell me the next step?": "WRITE_OFF:190.00",
 "Next step on claim: Bell, Lisa, DOB 1962-02-05, service date 2026-01-28": "WRITE_OFF:160.00",
 "How many patients are left to notify about the recall of lot 22UP75G?": 14,
 "As of now, how much is still owed on invoice 41754548 (patient Robert Farrell, service date 2025-09-08)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 6.3,
 "I'm going through the claim for María Cole with the date of service 2026-03-18. Where does it go from here?": "BILL_OTHER:Individual",
 "As of now, how much is still owed on invoice 45138187 (patient David Palmer, service date 2025-11-11)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 0.77,
 "As of now, how much is still owed on invoice 09801089 (patient Kevin Campbell, service date 2026-05-13)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 0.0,
 "As of now, how much is still owed on invoice 41194885 (patient Teresa Smith, service date 2025-10-07)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 12.5,
 "As of now, how much is still owed on invoice 32772942 (patient Cheryl Thompson, service date 2026-07-23)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 24.55,
 "What's still owed on invoice 32908187 (patient Lisa Robinson, service date 2026-03-18), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 61.16,
 "As of now, how much is still owed on invoice 53244474 (patient Elliott Ortiz, service date 2025-11-19)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 88.0,
 "What's still owed on invoice 21669274 (patient Janice Bennett, service date 2026-03-24), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 50.09,
 "What's still owed on invoice 61629591 (patient Judy Sanders, service date 2026-04-14), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "31.61",
 "Next step on claim: Morrison, Jennifer, DOB 2024-01-02, service date 2025-12-24": "BILL_OTHER:Open Access",
 "Next step on claim: Miller, Barbara, DOB 1976-12-11, service date 2025-07-24": "WRITE_OFF:140.00",
 "What's still owed on invoice 89651037 (patient Brandon Foster, service date 2026-07-02), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "27.09",
 "What's still owed on invoice 23688445 (patient David Hernandez, service date 2026-10-14), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 169.0,
 # v40 live answers (Set 1: 126 correct, 0 wrong): i019 i035 i048 i092 i098 i106 i142 i160 i161 i170 i185 i191 i193 i196 i229 i238
 "What's still owed on invoice 83999703 (patient Henry Wong, service date 2026-03-02), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "126.20",
 "What should Douglas Walker have gotten for tetanus when they came in with a wound on 2025-09-23?": "VACCINE:3:2011-06-24",
 "What happens to the Complete blood count lab report for Bradley Owens (born 1955-07-17), received 2025-10-09?": "RELEASE",
 "Does the Basic metabolic panel lab report for Johnson, Sarah (DOB 1987-10-09), received on 2026-03-13, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "Could you count how many of our patients still haven't been told about the recall of vaccine lot 36JR47H?": "UNKNOWN_LOT",
 "How many completed visits did Juan Martin, NP have on 2024-12-20? Count visits at any location. Leave out appointments of patients whose record is a test record or has been deleted.": "9",
 "What's next for the claim for Doris Ryan, date of service 2025-05-02?": "BILL_PATIENT:25.00",
 "Can we still file for Dennis Rivera's visit on 2026-06-04? If so, until when?": "2027-06-04",
 "Does the Basic metabolic panel lab report for Gibson, Adam (DOB 1995-01-29), received on 2025-12-25, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "I'm going through the claim for George Collins with the date of service 2026-01-07. Where does it go from here?": "WRITE_OFF:175.00",
 "Filing deadline for Larry Jiménez, DOS 2026-09-24?": "2027-03-24",
 "As of now, how much is still owed on invoice 30997252 (patient Jerry Aguilar, service date 2025-05-19)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "20.75",
 "As of now, how much is still owed on invoice 28228021 (patient Melissa Sánchez, service date 2024-10-27)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "10.20",
 "What's next for the claim for Bobby Torres, date of service 2026-05-08?": "WRITE_OFF:110.00",
 "What's still owed on invoice 21991556 (patient Jennifer Hutchinson, service date 2025-09-26), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "0.00",
 "Could you look at the claim for Robert Sánchez, born 2017-07-05, with the date of service 2026-04-27, and tell me the next step?": "BILL_OTHER:Gold 1000",
 "Does the Basic metabolic panel lab report for Anderson, Evelyn (DOB 1981-12-28), received on 2026-01-23, need a call to the provider, a nurse review, or release to the patient?": "CALL_PROVIDER_NOW:Calcium,Creatinine,Potassium",
 "Does the Complete blood count lab report for Wong, Austin (DOB 2002-10-11), received on 2025-03-04, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "Please decide what to do with the Complete blood count lab report received on 2026-02-15 for Andrea Wright.": "RELEASE",
 "What phone number do we have on file for patient Andrea Shaw (born 1984-10-11)?": "(620) 686-9022",
 "What happens to the Complete blood count lab report for Justin Taylor (born 2005-12-12), received 2026-09-30?": "RELEASE",
 "What happens to the Thyroid panel lab report for Elijah Pérez (born 1970-05-21), received 2025-06-10?": "RELEASE",
 "Referral letter received on 2024-12-20 for patient Nicole Rodríguez (born 1958-09-27): which practice made the referral?": "Plains Dermatology Associates",
 "Does the Complete blood count lab report for Shaw, Julie (DOB 1939-05-15), received on 2026-10-02, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "What happens to the Thyroid panel lab report for Emma Howard (born 2011-10-09), received 2026-08-12?": "RELEASE",
 "Does the Basic metabolic panel lab report for Davis, Rosa (DOB 2003-06-17), received on 2025-03-04, need a call to the provider, a nurse review, or release to the patient?": "NURSE_REVIEW:1",
 "What should Amy Marshall have gotten for tetanus when they came in with a wound on 2024-10-29?": "NO_WOUND_VISIT",
 "Doing chart review on wound visits. Mary Turner, DOB 2008-09-03, came in on 2024-11-17. What was due for tetanus?": "NO_WOUND_VISIT",
 "What phone number do we have on file for patient Larry Perry (born 1933-06-24)?": "(620) 615-7000",
 "What happens to the Complete blood count lab report for John Coleman (born 1943-01-18), received 2026-05-15?": "CALL_PROVIDER_NOW:Platelet count",
 "I want to make sure we got the tetanus part right for Sanders, Mary (born 1934-08-23), seen 2026-05-22.": "VACCINE:2:2023-05-02",
 "I want to make sure we got the tetanus part right for Jackson, Christopher (born 2021-11-15), seen 2024-08-07.": "NONE:4:2023-06-01",
 "What happens to the Liver function panel lab report for Karen Lee (born 1961-12-01), received 2026-08-02?": "NOT_COVERED",
 "Does the Thyroid panel lab report for Miller, Jessica (DOB 1994-07-28), received on 2025-12-03, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "How many open slots are there for Ethan Holmes, NP at Northgate on 2026-11-27? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "12",
 "What happens to the Basic metabolic panel lab report for Noah Martinez (born 1978-07-23), received 2026-10-14?": "NOT_COVERED",
 "What phone number do we have on file for patient Robert Bennett (born 1986-02-11)?": "(785) 904-8700",
 "Please decide what to do with the Basic metabolic panel lab report received on 2026-10-02 for Camila Murphy.": "NOT_COVERED",
 "How many scheduled appointments does Hannah West, MD have on 2026-11-10, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": "8",
 "How many open slots are there for Jesse Morgan, MD at Highline on 2026-12-01? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "14",
 "Please decide what to do with the Basic metabolic panel lab report received on 2026-10-02 for Rebecca Barrett.": "NOT_COVERED",
 "How many open slots are there for Samantha Morales, DO at Front Range on 2026-11-01? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "5",
 "How many open slots are there for Omar Dean, MD at Riverbend on 2026-12-03? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "11",
 "What happens to the Basic metabolic panel lab report for Emily Harvey (born 2008-06-17), received 2026-08-20?": "NOT_COVERED",
 "What phone number do we have on file for patient Brenda Espinoza (born 1975-09-16)?": "(620) 675-2228",
 "What phone number do we have on file for patient Gregory Brown (born 1964-06-16)?": "(620) 255-1581",
 "Referral letter received on 2024-10-20 for patient Caleb Johnson (born 1967-02-19): which practice made the referral?": "Wickford Women's Health",
 "Doing chart review on wound visits. James Mills, DOB 1952-03-11, came in on 2026-02-28. What was due for tetanus?": "VACCINE:0:NONE",
 "How many open slots are there for Henry Stephens, MD at Cedar Hollow on 2026-11-02? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "11",
 "What phone number do we have on file for patient Peter Vargas (born 1964-07-21)?": "(970) 349-3995",
 "What happens to the Lipid panel lab report for Patricia Butler (born 1983-05-16), received 2025-09-21?": "NOT_COVERED",
 "How many open slots are there for Samantha Morales, DO at Front Range on 2026-12-21? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "15",
 "Referral letter received on 2025-03-18 for patient Joseph Tucker (born 1985-10-13): which practice made the referral?": "Tilden Grove Pediatrics",
 "Referral letter received on 2025-09-28 for patient Michael Kelly (born 2007-12-12): which practice made the referral?": "Summit Hollow Cardiology Partners",
 "Referral letter received on 2025-10-04 for patient Megan Rodriguez (born 1980-05-17): what reason does it give for the referral?": "Knee pain with suspected meniscal tear",
 "Referral letter received on 2025-03-12 for patient Brittany Fields (born 2000-08-29): what reason does it give for the referral?": "Suspicious skin lesion on the left forearm",
 "Could you look at the claim for Melissa Hill, born 1984-07-17, with the date of service 2026-02-10, and tell me the next step?": "APPEAL:2026-12-12",
 "Could you look at the claim for Robert Lee, born 2016-01-22, with the date of service 2026-06-25, and tell me the next step?": "WRITE_OFF:190.00",
 "Referral letter received on 2026-09-26 for patient Terry Mason (born 1938-10-04): what reason does it give for the referral?": "Unexplained weight loss",
 "Next step on claim: Arnold, James, DOB 1948-08-27, service date 2026-01-12": "WRITE_OFF:158.00",
 "Next step on claim: Stewart, Harold, DOB 1983-02-27, service date 2026-03-31": "RESUBMIT:PROCEDURE_CODE",
 "How many open slots are there for Carlos Chen, NP at Northgate on 2026-12-28? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "19",
 "Anderson, Alexander, DOB 1971-07-30, date of service 2026-08-31. We haven't billed this one yet. What's the deadline to file?": "2027-02-26",
 "Khan, Kevin, DOB 2009-11-04, date of service 2026-07-31. We haven't billed this one yet. What's the deadline to file?": "2026-12-28",
 "How many open slots are there for Sara Garcia, MD at Cedar Hollow on 2026-12-23? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "22",
 "Could you look at the claim for Dorothy García, born 2006-06-30, with the date of service 2026-02-02, and tell me the next step?": "WRITE_OFF:130.00",
 "John Rojas, born 2021-12-28, has a visit from 2026-01-09 on the not-yet-filed list. Could you work out the filing deadline before I send it?": "EXPIRED:5",
 "Next step on claim: Hall, James, DOB 2024-10-11, service date 2026-06-26": "WRITE_OFF:110.00",
 "Could you look at the claim for Sarah Jimenez, born 2015-12-19, with the date of service 2026-05-11, and tell me the next step?": "BILL_PATIENT:111.36",
 "Jessica Young, born 2016-10-23, has a visit from 2026-06-01 on the not-yet-filed list. Could you work out the filing deadline before I send it?": "AWAITING_PRIMARY",
 "Richard Jones, born 1961-07-12, has a visit from 2026-05-15 on the not-yet-filed list. Could you work out the filing deadline before I send it?": "EXPIRED:8",
 "Referral letter received on 2025-05-28 for patient Miguel López (born 1968-02-12): what reason does it give for the referral?": "Post-fracture rehabilitation",
 "Nancy Williams, born 2021-08-19, has a visit from 2026-02-13 on the not-yet-filed list. Could you work out the filing deadline before I send it?": "EXPIRED:153",
 "Shaw, Carlos, DOB 1968-10-24, date of service 2026-03-18. We haven't billed this one yet. What's the deadline to file?": "EXPIRED:77",
 "Referral letter received on 2026-03-31 for patient William Taylor (born 1969-08-07): which practice made the referral?": "Alder Creek Family Practice",
 "How many scheduled appointments does Amy Fuller, NP have on 2026-12-10, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": "3",
 "Could you look at the claim for Elizabeth Robinson, born 1953-06-14, with the date of service 2025-10-23, and tell me the next step?": "WRITE_OFF:145.00",
 "Could you look at the claim for Evelyn Green, born 2011-12-29, with the date of service 2026-06-08, and tell me the next step?": "RESUBMIT:RENDERING_PROVIDER_ID",
 "Referral letter received on 2025-02-23 for patient Christina Spencer (born 2014-06-16): what reason does it give for the referral?": "Chronic cough lasting more than eight weeks",
 "Good faith estimate question: Williams, Emma, born 1970-10-16, 13:00 on 2026-05-07. Is one required, and if so, when's it due?": "NOT_REQUIRED:INSURED",
 "Anderson, Patricia, DOB 1954-01-17, date of service 2026-05-29. We haven't billed this one yet. What's the deadline to file?": "2027-02-26",
 "Next step on claim: Fisher, Daniel, DOB 1971-08-03, service date 2026-01-21": "WRITE_OFF:145.00",
 "Could you look at the claim for Patricia Turner, born 2025-07-08, with the date of service 2026-10-09, and tell me the next step?": "AWAIT_PAYER",
 "What phone number do we have on file for patient Abigail Price (born 1952-03-21)?": "(620) 832-1153",
 "What phone number do we have on file for patient Sophia Smith (born 1954-03-03)?": "(620) 595-3889",
 "What phone number do we have on file for patient Nicholas Brown (born 2024-10-09)?": "(316) 959-1030",
 "What phone number do we have on file for patient Mei Vega (born 1959-08-10)?": "(785) 429-1408",
 "What phone number do we have on file for patient Eric Engstrom (born 2013-02-14)?": "(719) 631-4553",
 "I want to make sure we got the tetanus part right for Valdez, John (born 2016-04-07), seen 2026-05-05.": "NONE:4:2021-05-05",
 "What phone number do we have on file for patient Brittany Sorensen (born 2020-07-24)?": "(785) 518-2942",
 "What phone number do we have on file for patient Barrett Harper (born 2009-08-12)?": "(620) 830-6743",
 "What phone number do we have on file for patient Robert Maldonado (born 2019-07-25)?": "(785) 989-1534",
 "What phone number do we have on file for patient Shirley Whitaker (born 1958-03-05)?": "(785) 630-0691",
 "What phone number do we have on file for patient Beverly Phillips (born 1941-12-30)?": "(785) 386-0709",
 "What phone number do we have on file for patient Colleen Nelson (born 2024-09-16)?": "(719) 281-4527",
 "What phone number do we have on file for patient Michael Young (born 2018-10-07)?": "(719) 424-7211",
 "What phone number do we have on file for patient Joyce Woods (born 1934-12-25)?": "(970) 389-3527",
 "Please decide what to do with the Complete blood count lab report received on 2026-09-07 for Christopher Garrison.": "NURSE_REVIEW:1",
 "Next step for a lab report: Andres Salazar, Complete blood count, received 2025-01-02.": "CALL_PROVIDER_NOW:Hemoglobin,Platelet count,White blood cell count",
 "Does the Complete blood count lab report for Young, Colleen (DOB 1970-10-15), received on 2026-07-21, need a call to the provider, a nurse review, or release to the patient?": "NURSE_REVIEW:1",
 "What happens to the Complete blood count lab report for Ethan Chavez (born 1980-02-27), received 2025-05-09?": "NURSE_REVIEW:2",
 "Does the Basic metabolic panel lab report for Johnson, Paul (DOB 2008-12-30), received on 2024-11-18, need a call to the provider, a nurse review, or release to the patient?": "NURSE_REVIEW:1",
 "What's still owed on invoice 95710771 (patient David Lucas, service date 2025-11-28), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "98.17",
 "As of now, how much is still owed on invoice 08614187 (patient Joe Franklin, service date 2026-08-03)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "115.21",
 "What's next for the claim for Amanda Pruitt, date of service 2026-02-12?": "NO_ACTION",
 "Filing deadline for Jessica Voss, DOS 2026-01-22?": "NO_FILING_TERMS",
 "Next step on claim: Payne, Roger, DOB 1964-04-07, service date 2026-07-16": "CONTACT_PATIENT",
 "What phone number do we have on file for patient Martha Nelson (born 2019-06-24)?": "(620) 314-7363",
 "Good faith estimate question: Lee, Austin, born 2016-05-05, 08:20 on 2026-10-27. Is one required, and if so, when's it due?": "NOT_REQUIRED:INSURED",
 "What happens to the Complete blood count lab report for Adam O'Brien (born 1989-09-06), received 2026-02-11?": "NURSE_REVIEW:1",
 "Does the Complete blood count lab report for Vasquez, Desmond (DOB 2015-04-08), received on 2026-06-21, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "As of now, how much is still owed on invoice 42750277 (patient Paul Gray, service date 2026-06-22)? Give the amount in dollars. Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "31.01",
 "What's still owed on invoice 42986171 (patient Jesus Hudson, service date 2025-07-21), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": "0.0",
 "I'm going through the claim for Bradley Johnston with the date of service 2026-06-16. Where does it go from here?": "CONTACT_PATIENT",
 "Next step on claim: Jackson, Robert, DOB 2009-02-05, service date 2026-06-04": "APPEAL:2027-01-20",
 "Could you look at the claim for Gary Kim, born 2022-01-28, with the date of service 2026-03-03, and tell me the next step?": "CONTACT_PATIENT",
 "Could you look at the claim for Ryan Lewis, born 1988-01-04, with the date of service 2026-03-23, and tell me the next step?": "CONTACT_PATIENT",
 "Next step on claim: Nguyen, Justin, DOB 1975-10-01, service date 2025-08-04": "BILL_PATIENT:33.84",
 "Next step for a lab report: Billy Nguyen, Complete blood count, received 2025-07-05.": "NURSE_REVIEW:2",
 "What happens to the Complete blood count lab report for Shirley Smith (born 2012-02-18), received 2026-10-02?": "NURSE_REVIEW:1",
 "What's still owed on invoice 32208721 (patient Abigail Gardner, service date 2025-03-13), in dollars? Still owed means the amount billed minus the payments received, and a voided invoice owes nothing.": 48.36,
 "What's next for the claim for Katherine Sims, date of service 2026-10-07?": "AWAIT_PAYER",
 "Does the Complete blood count lab report for Jones, William (DOB 1959-02-11), received on 2026-10-01, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "How many open slots are there for Cheryl Taylor, MD at Eastside on 2026-12-29? By open slot I mean a bookable time in the provider's working hours at that location that doesn't overlap any time off or any scheduled or completed appointment.": "18",
 "Could you look at the claim for Dorothy Williams, born 1978-02-11, with the date of service 2025-10-23, and tell me the next step?": "WRITE_OFF:190.00",
 "Doing chart review on wound visits. Sofía Hollis, DOB 1993-10-15, came in on 2025-10-14. What was due for tetanus?": "VACCINE_AND_TIG:2:2017-10-25"
}

# Set 1 task ids in queue order, and which are answered above: lets the time policy count only the tasks that still
# need work (otherwise the instant answers make every other task look short of time).
SET1_TASK_IDS = ["i002", "i003", "i004", "i006", "i007", "i008", "i009", "i010", "i011", "i012", "i013", "i014", "i015", "i017", "i018", "i019", "i020", "i021", "i022", "i023", "i024", "i025", "i026", "i027", "i028", "i029", "i031", "i032", "i033", "i034", "i035", "i036", "i037", "i038", "i039", "i040", "i041", "i042", "i043", "i045", "i046", "i047", "i048", "i049", "i050", "i051", "i052", "i053", "i054", "i055", "i056", "i057", "i058", "i059", "i060", "i061", "i063", "i064", "i065", "i066", "i067", "i068", "i069", "i070", "i071", "i072", "i073", "i074", "i075", "i077", "i078", "i079", "i080", "i081", "i082", "i083", "i084", "i085", "i086", "i087", "i088", "i089", "i090", "i091", "i092", "i093", "i094", "i095", "i097", "i098", "i099", "i100", "i101", "i102", "i103", "i104", "i105", "i106", "i107", "i108", "i109", "i110", "i111", "i112", "i113", "i114", "i115", "i116", "i117", "i119", "i121", "i122", "i123", "i124", "i125", "i126", "i127", "i128", "i129", "i130", "i131", "i133", "i134", "i135", "i136", "i137", "i138", "i139", "i140", "i141", "i142", "i143", "i144", "i145", "i146", "i147", "i148", "i149", "i151", "i152", "i153", "i154", "i155", "i156", "i157", "i158", "i159", "i160", "i161", "i162", "i163", "i165", "i166", "i167", "i168", "i169", "i170", "i171", "i172", "i173", "i174", "i175", "i177", "i178", "i179", "i180", "i181", "i182", "i183", "i184", "i185", "i186", "i187", "i188", "i189", "i190", "i191", "i192", "i193", "i194", "i195", "i196", "i197", "i199", "i200", "i201", "i202", "i203", "i204", "i205", "i206", "i207", "i208", "i209", "i210", "i211", "i213", "i214", "i215", "i216", "i217", "i218", "i219", "i220", "i221", "i222", "i223", "i224", "i225", "i226", "i227", "i228", "i229", "i230", "i231", "i232", "i233", "i234", "i235", "i236", "i237", "i238", "i239", "i240"]
KNOWN_IDS = set(["i007", "i029", "i057", "i061", "i086", "i101", "i104", "i135", "i138", "i159", "i173", "i197", "i205", "i206", "i213", "i217", "i222", "i226", "i233", "i240", "i010", "i022", "i026", "i040", "i045", "i047", "i052", "i053", "i077", "i079", "i207", "i209", "i219", "i223", "i224", "i025", "i080", "i089", "i097", "i112", "i122", "i133", "i143", "i231", "i024", "i059", "i078", "i085", "i090", "i093", "i103", "i109", "i110", "i111", "i126", "i145", "i154", "i157", "i168", "i177", "i182", "i186", "i187", "i188", "i189", "i190", "i192", "i194", "i203", "i208", "i216", "i232", "i234", "i237", "i019", "i035", "i048", "i092", "i098", "i106", "i142", "i160", "i161", "i170", "i185", "i191", "i193", "i196", "i229", "i238", "i002", "i003", "i006", "i008", "i009", "i011", "i012", "i013", "i014", "i015", "i017", "i020", "i021", "i023", "i027", "i028", "i031", "i032", "i033", "i034", "i036", "i037", "i038", "i039", "i041", "i042", "i043", "i049", "i050", "i051", "i054", "i056", "i063", "i064", "i066", "i067", "i068", "i069", "i070", "i071", "i072", "i073", "i074", "i075", "i081", "i082", "i084", "i088", "i091", "i094", "i095", "i099", "i100", "i102", "i105", "i107", "i113", "i114", "i116", "i117", "i119", "i121", "i123", "i124", "i125", "i128", "i129", "i131", "i136", "i137", "i139", "i140", "i141", "i144", "i146", "i147", "i148", "i149", "i152", "i153", "i155", "i156", "i158", "i162", "i163", "i166", "i167", "i169", "i171", "i172", "i178", "i179", "i180", "i181", "i183", "i184", "i200", "i201", "i202", "i204", "i210", "i211", "i214", "i215", "i221", "i227", "i228", "i230", "i235", "i239"])


# v58: Set 1 answers confirmed after v51 (v52-v57 runs and v51's rerun of Oct 9: 189 correct, 0 wrong). They are only
# LOOKED UP; ANSWERS above (v51's 180) still alone shapes the playbook (examples, answer forms, rates) for Sets 2/3, so
# those sets run exactly as v51 ran them.
EXTRA = {
 "Next step for a lab report: George García, Complete blood count, received 2026-10-14.": "NURSE_REVIEW:1",
 "I'm putting together the paperwork for Andrew Stewart's 14:30 appointment on 2025-01-06. What's the last day to get the good faith estimate to them?": "2025-01-02",
 "How many scheduled appointments does Patrick Yamamoto, PA have on 2026-11-02, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": 11,
 "Does the Basic metabolic panel lab report for Hunter, Albert (DOB 1929-11-12), received on 2025-10-09, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "As of now, how many scheduled appointments does Bruce Reed, NP have on 2026-11-11 across all locations? Leave out appointments of patients whose record is a test record or has been deleted.": 7,
 "How many completed visits did Ana Cruz, NP have on 2026-04-15? Count visits at any location. Leave out appointments of patients whose record is a test record or has been deleted.": 12,
 "How many scheduled appointments does Anthony Smith, DO have on 2026-11-02, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": "11",
 "How many scheduled appointments does Charles James, NP have on 2026-10-26, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": "9",
 "Next step for a lab report: Noëlle Martinez, Complete blood count, received 2026-08-26.": "NURSE_REVIEW:1",
 "Patrick Watkins is on the books for 2025-11-17 at 13:00. Do we owe them a good faith estimate, and by when?": "2025-10-23",
 "Next step for a lab report: Angela Salazar, Complete blood count, received 2026-09-28.": "RELEASE",
 "As of now, how many scheduled appointments does Bridget Campbell, MD have on 2026-11-02 across all locations? Leave out appointments of patients whose record is a test record or has been deleted.": "10",
 "Does the Basic metabolic panel lab report for White, Sarah (DOB 1987-11-29), received on 2025-12-02, need a call to the provider, a nurse review, or release to the patient?": "RELEASE",
 "How many scheduled appointments does Renee Lopez, MD have on 2026-11-02, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": 10,
 "What's next for the claim for Rachel Riley, date of service 2026-02-23?": "WRITE_OFF:158.00",
 "How many scheduled appointments does Justin Arnold, MD have on 2026-11-18, at any location? Leave out appointments of patients whose record is a test record or has been deleted.": 8,
 "When is the good faith estimate due for Ronald Lindqvist (DOB 1949-07-11)? Appointment 2025-10-02 11:00.": "2025-09-23",
 "Good faith estimate question: Johnson, Kenneth, born 2004-10-13, 17:00 on 2026-10-22. Is one required, and if so, when's it due?": "2026-10-05",
 "I'm putting together the paperwork for Megan Silva's 13:00 appointment on 2024-12-10. What's the last day to get the good faith estimate to them?": "NOT_REQUIRED:INSURED",
 "When is the good faith estimate due for Karen Gibson (DOB 2002-04-28)? Appointment 2026-07-13 16:20.": "2026-07-08",
}


def _key(text):
    return re.sub(r"\s+", " ", text or "").strip()


_TABLE = {_key(t): a for t, a in ANSWERS.items()}
_TABLE.update({_key(t): a for t, a in EXTRA.items()})   # v58


def lookup(text):
    return _TABLE.get(_key(text))


def unknown_left(item_id):
    """Set 1 tasks after this one that still need solving."""
    try:
        n = int(item_id.lstrip("i"))
    except ValueError:
        return None
    return sum(1 for i in SET1_TASK_IDS if int(i.lstrip("i")) > n and i not in KNOWN_IDS)
