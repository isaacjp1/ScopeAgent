"""Self-checks for the deterministic logic (no browser, no network): python3 test/test_logic.py"""
import asyncio
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent import clinic, config  # noqa: E402
from agent.fast import DOC_TASK, NE_TASK, PHONE_OTHER, PHONE_TASK, WHO_REFERRED, dates_in  # noqa: E402
from agent.rules import check_ne  # noqa: E402
from agent.solver import plausible  # noqa: E402

MSG = json.load(open(os.path.join(os.path.dirname(__file__), "..", "practice_items.json")))[0]["text"]
GOOD = {"years": 3, "counting_statuses": ["Completed"], "excluded_services": ["Lab draw", "X-ray"],
        "same_specialty_counts": True, "all_locations": True, "window": "standard", "new_answer": "NEW",
        "established_example": "ESTABLISHED:2025-03-11", "other_conditions": []}


def main():
    # rule compile check: accepts the practice rule, rejects anything not in the text or unusual
    r = check_ne(GOOD, MSG)
    assert r == {"years": 3, "statuses": ["Completed"], "excluded": ["Lab draw", "X-ray"], "new": "NEW", "prefix": "ESTABLISHED:"}, r
    assert check_ne({**GOOD, "excluded_services": ["Lab draw", "Massage"]}, MSG) is None
    assert check_ne({**GOOD, "other_conditions": ["telehealth never counts"]}, MSG) is None
    assert check_ne({**GOOD, "established_example": "EST:2025-03-11"}, MSG) is None
    assert check_ne({**GOOD, "years": "x"}, MSG) is None
    assert check_ne(None, MSG) is None

    # 3-year window, Feb 29
    assert clinic.window(dt.date(2026, 11, 5), 3) == (dt.date(2023, 11, 6), dt.date(2026, 11, 4))
    assert clinic.window(dt.date(2028, 2, 29), 3) == (dt.date(2025, 3, 1), dt.date(2028, 2, 28))

    # task routing
    t1 = "Is Judith Jackson (born 2004-11-12) new or established for Kenneth Sullivan, NP on 2028-07-20?"
    t2 = "On 2026-12-25 there is a visit with Douglas Hughes, MD for Henry, Peter, DOB 1975-06-23, and I need new vs. established for it."
    t3 = "What phone number do we have on file for patient Carol Jones (born 1982-09-07)?"
    t4 = "Referral letter received on 2025-09-16 for patient Gregory Porter (born 1976-04-08): what reason does it give for the referral?"
    assert NE_TASK.search(t1) and NE_TASK.search(t2) and not NE_TASK.search(t3)
    assert PHONE_TASK.search(t3) and not PHONE_OTHER.search(t3)
    assert PHONE_OTHER.search("What is the phone number of the practice that referred Carol Jones (born 1982-09-07)?")
    assert DOC_TASK.search(t4) and not DOC_TASK.search(t3)
    assert WHO_REFERRED.search("Referral letter received on 2024-12-01 for patient Ana Corbett: which practice made the referral?")
    assert not WHO_REFERRED.search(t4)
    m = re.search(r"(?:^| \| )referral letter from (.+?)(?: \||$)","Dec 1, 2024 | Referral letter | Referral letter from Granite Fork Internal Medicine | View", re.I)
    assert m and m.group(1) == "Granite Fork Internal Medicine", m
    assert dates_in(t2) == [dt.date(2026, 12, 25), dt.date(1975, 6, 23)]
    assert dates_in("seen Mar 4, 2026 and 03/05/2026") == [dt.date(2026, 3, 4), dt.date(2026, 3, 5)]

    # answer shape checks
    assert plausible("How many patients named Jones?", "12") and not plausible("How many patients named Jones?", "twelve")
    assert plausible(t3, "(785) 310-6041") and not plausible(t3, "310-6041")
    assert not plausible("Who referred her?", "None") and not plausible("x", "")
    assert plausible("Which providers?", ["A", "B"])

    # phone: the learned digit map is trusted only after 3 agreeing screenshots, and re-checked every 8th read
    class FakeSite:
        digit_map, digit_map_ok, digit_map_hits, phone_reads = {}, True, 0, 0
        shots = 0
        scramble = str.maketrans("0123456789", "9876543210")
        true_phones = {"/patients/a": "(785) 310-6041", "/patients/b": "(620) 555-0198", "/patients/c": "(719) 244-3871"}

        def _normalize(self, p):
            return p

        async def read(self, path, all_pages=True):
            return {"text": "Contact\nPhone\n" + self.true_phones[path].translate(self.scramble) + "\n"}

        async def screenshot(self, path):
            self.shots += 1
            self.last = path
            return "data:image/jpeg;base64,xx"

    class FakeLLM:
        async def chat(self, messages, **kw):
            return {"content": json.dumps({"phone": site.true_phones[site.last]})}, {}, 0

    site, llm = FakeSite(), FakeLLM()

    async def run():
        out = []
        for p in ["/patients/a", "/patients/b", "/patients/c", "/patients/a", "/patients/b", "/patients/c", "/patients/a"]:
            res = await clinic.patient_contact(site, llm, p)
            out.append((res["phone"], res["safe_to_answer"]))
        return out
    res = asyncio.run(run())
    assert all(ok and phone == site.true_phones[p] for (phone, ok), p in
               zip(res, ["/patients/a", "/patients/b", "/patients/c", "/patients/a", "/patients/b", "/patients/c", "/patients/a"])), res
    assert site.shots < 7, site.shots     # later reads decoded without a screenshot

    assert config.task_cap(900, 225) == 10.0 and config.task_cap(30, 225) == config.MIN_TASK_SECONDS
    print("all logic checks passed")


if __name__ == "__main__":
    main()
