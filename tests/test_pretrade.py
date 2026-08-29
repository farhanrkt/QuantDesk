"""The pre-trade check panel.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. No aggregate, ever. A count, a score or a severity order is a composite in
   the one field everybody reads, and it is the direction any later change to
   this panel will drift in. The assertion is on the KEY SET rather than on the
   wording, so adding `"score"` fails the build rather than shipping quietly.

2. Absence of a flag never reads as evidence of quality. The framing sentence
   that says so must survive every state, and the state it matters most in — the
   empty one — is the state where nothing else on the panel says anything.

3. Not tested is not clear. A refused lens, a failed leg and a missing filing
   land in `notChecked` and never in silence.

4. An uncalibrated check does not appear. A flag without a base rate is not
   interpretable, and this is the rule that keeps the panel from growing
   conditions faster than anybody measures them.

5. Nothing here is ever green. There is no pass state to colour, so a `good`
   tone would be a claim the module has no basis for.

The wording is free to change. Those five are not.
"""

from __future__ import annotations

import pytest

from _lib import explain as E
from _lib import pretrade as P


# --------------------------------------------------------------------------- #
# Payload builders — the confluence leg shapes the predicates read
# --------------------------------------------------------------------------- #
def leg(data, ok=True, error=None):
    return {"ok": ok, "data": data} if ok else {"ok": False, "error": error}


def quality(applicable=True, altman="safe", altman_score=6.2, beneish="clean",
            beneish_score=-2.6, piotroski_band="solid", score=7,
            signals_available=9, indices_available=8):
    if not applicable:
        return leg({"applicable": False, "cause": "financial",
                    "reason": "Piotroski, Altman and Beneish were all built on "
                              "non-financial firms."})
    return leg({
        "applicable": True,
        "piotroski": {"score": score, "maxScore": 9, "band": piotroski_band,
                      "signalsAvailable": signals_available, "signalsTotal": 9},
        "altman": {"score": altman_score, "band": altman},
        "beneish": {"score": beneish_score, "band": beneish,
                    "indicesAvailable": indices_available, "indicesTotal": 8},
    })


def valuation(terminal=0.35, implied=0.09, assumed=0.10, manual=None):
    return leg({
        "baseCase": {"terminalShare": terminal, "impliedGrowth": implied,
                     "assumedGrowth": assumed},
        "assumptions": {"manualApplied": manual or {}},
    })


def technical(has_long=True, hurst="persistent", hurst_value=0.61, max_dd=-0.28):
    return leg({
        "hasLongTerm": has_long,
        "longTerm": {
            "hurstReading": {"hurst": hurst_value, "verdict": hurst,
                             "randomWalkLow": 0.43, "randomWalkHigh": 0.57},
            "drawdown": {"usable": True, "maxDrawdown": max_dd,
                         "timeUnderWaterDays": 354},
        },
    })


def anomaly(resolved=True, inside=False, ratio=6.0):
    return leg({"liquidity": {"spreadResolved": resolved, "insideSpreadNoise": inside,
                              "moveVsSpread": ratio}})


def payload(**kw):
    base = {"quality": quality(), "valuation": valuation(),
            "technical": technical(), "anomaly": anomaly()}
    base.update(kw)
    return base


def calibration(rate=0.06, sample=200, only=None, markets=None, **rates):
    """Every check calibrated at `rate`, with named overrides.

    `only` restricts which checks are calibrated at all, which is how the
    uncalibrated path is exercised. `markets` is {check_id: {market: entry}} for
    the per-market rates the real calibration writes.
    """
    ids = only if only is not None else [c["id"] for c in P.CHECKS]
    checks = {
        check_id: {"firingRate": rates.get(check_id, rate),
                   "sampleSize": sample, "couldNotRun": 4,
                   "markets": (markets or {}).get(check_id, {})}
        for check_id in ids
    }
    return {"measuredOn": "2026-08-28", "universeLabel": "four index universes",
            "marketLabels": {"US": "the Dow and the Nasdaq-100",
                             "ID": "IDX30 and LQ45"},
            "universes": ["Dow Jones Industrial Average"], "baseRateMax": P.BASE_RATE_MAX,
            "checks": checks}


def assess(pl=None, cal=None, market=None):
    return P.assess(pl if pl is not None else payload(),
                    cal if cal is not None else calibration(), market=market)


def fired_ids(result) -> list[str]:
    return [f["id"] for f in result["flags"]]


def all_text(result) -> str:
    parts = [result["headline"], result["framing"], result["caveat"]]
    parts += list(result["notes"].values())
    for entry in result["flags"] + result["baseConditions"]:
        parts += [entry["rateSentence"], entry["explain"]["reading"],
                  entry["explain"]["action"], entry["explain"]["what"]]
    parts += [n["reason"] for n in result["notChecked"]]
    return " ".join(p for p in parts if p).lower()


# --------------------------------------------------------------------------- #
# 1. No aggregate, under any input
# --------------------------------------------------------------------------- #
# Any of these appearing at the top level or on a check would be a composite
# arriving by the back door. The panel's whole claim is that three flags on one
# company and two on another are not comparable quantities.
AGGREGATE_KEYS = {"score", "total", "passed", "count", "severity", "rating",
                  "grade", "verdict", "rank", "composite", "tally", "summary",
                  "overall", "riskScore", "flagCount"}


@pytest.mark.parametrize("altman", ["safe", "grey", "distress"])
@pytest.mark.parametrize("beneish", ["clean", "borderline", "flagged"])
@pytest.mark.parametrize("piotroski_band", ["strong", "mixed", "weak"])
def test_no_input_ever_produces_an_aggregate(altman, beneish, piotroski_band):
    result = assess(payload(quality=quality(altman=altman, beneish=beneish,
                                            piotroski_band=piotroski_band)))
    assert not (set(result) & AGGREGATE_KEYS), sorted(set(result) & AGGREGATE_KEYS)
    for entry in result["flags"] + result["baseConditions"]:
        assert not (set(entry) & AGGREGATE_KEYS), sorted(set(entry) & AGGREGATE_KEYS)


def test_the_framing_never_counts_what_fired():
    """A tally in prose is a tally. Three flags must not read as a worse number
    than one, and the only defence is that no number is offered."""
    heavy = assess(payload(
        quality=quality(altman="distress", beneish="flagged", piotroski_band="weak"),
        technical=technical(hurst="indistinguishable", max_dd=-0.62),
    ))
    assert len(heavy["flags"]) >= 4, fired_ids(heavy)
    for text in (heavy["framing"], heavy["headline"]):
        assert not any(ch.isdigit() for ch in text), text


# --------------------------------------------------------------------------- #
# 2. Absence is never evidence
# --------------------------------------------------------------------------- #
def test_a_clean_company_is_told_that_clean_is_not_a_verdict():
    result = assess()
    assert result["flags"] == []
    assert E.ABSENCE_IS_NOT_EVIDENCE in result["caveat"]
    assert "not a clean bill of health" in all_text(result)
    assert "None of the conditions" in result["framing"]


def test_demoted_conditions_are_still_true_and_the_framing_says_so():
    """A base condition APPLIES to this company; it has just been judged
    ordinary. Telling a reader nothing was true of it would be a plain error,
    and it is the one a two-branch framing makes."""
    result = assess(payload(quality=quality(altman="distress")),
                    calibration(altmanDistress=P.BASE_RATE_MAX + 0.2))
    assert result["flags"] == [] and result["baseConditions"]
    assert "None of the conditions" not in result["framing"]
    # The guarantee is that the framing AFFIRMS these are true of this company
    # rather than implying nothing was found. Wording shortened in the v2 copy
    # pass; this file's own docstring says wording is free to change.
    assert "true here" in result["framing"]


@pytest.mark.parametrize("pl", [
    {},
    {"quality": quality(applicable=False)},
    {"quality": quality(altman="distress")},
    {"technical": technical(has_long=False)},
    {"valuation": leg(None, ok=False, error="No usable market data.")},
])
def test_the_absence_sentence_survives_every_state(pl):
    result = assess(payload(**pl) if pl else {})
    assert E.ABSENCE_IS_NOT_EVIDENCE in result["caveat"]


def test_nothing_is_ever_green():
    """There is no pass state on this panel, so there is nothing to colour good."""
    result = assess(payload(
        quality=quality(altman="distress", beneish="flagged", piotroski_band="weak",
                        signals_available=7, indices_available=6),
        valuation=valuation(terminal=0.82, implied=0.31, manual={"base": True}),
        technical=technical(hurst="indistinguishable", max_dd=-0.66),
        anomaly=anomaly(inside=True, ratio=1.2),
    ))
    assert result["flags"], "expected this payload to fire several checks"
    for entry in result["flags"] + result["baseConditions"]:
        assert entry["explain"]["tone"] in ("warn", "bad", "neutral"), entry["id"]
        assert entry["explain"]["band"] in ("caution", "bad", "context"), entry["id"]


# --------------------------------------------------------------------------- #
# 3. Not tested is not clear
# --------------------------------------------------------------------------- #
def test_a_bank_lands_in_not_checked_rather_than_in_silence():
    result = assess(payload(quality=quality(applicable=False)))
    unchecked = {n["id"] for n in result["notChecked"]}
    assert {"altmanDistress", "beneishFlagged", "piotroskiWeak"} <= unchecked
    assert all(c not in fired_ids(result) for c in unchecked)
    # And the reason must be the refusal, not a shrug.
    reason = next(n for n in result["notChecked"] if n["id"] == "altmanDistress")["reason"]
    assert "designed refusal" in reason


def test_a_failed_leg_lands_in_not_checked():
    result = assess(payload(valuation=leg(None, ok=False, error="Yahoo has no price.")))
    unchecked = {n["id"] for n in result["notChecked"]}
    assert {"terminalDominant", "impliedGrowthDemanding"} <= unchecked


def test_a_short_range_removes_the_price_checks_rather_than_passing_them():
    result = assess(payload(technical=technical(has_long=False)))
    unchecked = {n["id"] for n in result["notChecked"]}
    assert {"hurstRandomWalk", "deepDrawdownHistory"} <= unchecked
    assert "widen the chart range" in all_text(result)


def test_an_unresolved_spread_is_not_checked_and_says_the_cost_is_small():
    """The estimator's own noise floor must not be reported as a large cost."""
    result = assess(payload(anomaly=anomaly(resolved=False, inside=True)))
    reason = next(n for n in result["notChecked"] if n["id"] == "moveInsideCost")["reason"]
    assert "the cost is small" in reason
    assert "moveInsideCost" not in fired_ids(result)


def test_every_not_checked_entry_names_where_to_look():
    result = assess(payload(quality=quality(applicable=False), technical=technical(has_long=False)))
    assert result["notChecked"]
    for entry in result["notChecked"]:
        assert entry["where"] and entry["reason"] and entry["label"]
        # Reasons are written unpunctuated: the panel renders them as
        # "<label>. <reason>." and a reason carrying its own stop doubles it.
        assert not entry["reason"].endswith("."), entry["id"]


def test_a_bank_gets_a_reason_per_model_rather_than_the_same_paragraph_thrice():
    """The shared refusal is one paragraph covering all three screens, which is
    right where it appears once. Repeated three times in a list it teaches the
    reader to skip the one section that must not be skipped."""
    result = assess(payload(quality=quality(applicable=False)))
    reasons = {n["id"]: n["reason"] for n in result["notChecked"]}
    assert len(set(reasons.values())) == 3, reasons
    assert "manufacturers" in reasons["altmanDistress"]
    assert "receivables-and-inventory" in reasons["beneishFlagged"]
    assert "excluded financial firms" in reasons["piotroskiWeak"]


def test_missing_statements_reads_differently_from_a_designed_refusal():
    """One is a decision, the other is a data gap somebody might be able to
    close. Rendering them alike devalues the decision."""
    gap = leg({"applicable": False, "cause": "no-statements",
               "reason": "No financial statements came back for this listing."})
    reasons = {n["id"]: n["reason"] for n in assess(payload(quality=gap))["notChecked"]}
    assert all("No financial statements came back" in r for r in reasons.values())
    assert not any("refuses a score" in r for r in reasons.values())


# --------------------------------------------------------------------------- #
# 4. Calibration governs what may appear at all
# --------------------------------------------------------------------------- #
def test_an_uncalibrated_check_never_renders_however_loudly_it_fires():
    result = assess(payload(quality=quality(altman="distress")),
                    calibration(only=["beneishFlagged"]))
    assert "altmanDistress" not in fired_ids(result)
    assert "altmanDistress" not in {n["id"] for n in result["notChecked"]}
    assert "altmanDistress" in {u["id"] for u in result["uncalibrated"]}
    # The guarantee is that the panel SAYS why it is holding one back, not the
    # phrasing it uses. Shortened in the v2 copy pass; the claim is unchanged.
    assert "withheld" in all_text(result)
    assert "base rate" in all_text(result)


def test_a_rate_measured_on_too_few_names_is_treated_as_no_rate():
    cal = calibration(sample=P.MIN_CALIBRATION_SAMPLE - 1)
    result = assess(payload(quality=quality(altman="distress")), cal)
    assert result["flags"] == []
    assert {u["id"] for u in result["uncalibrated"]} == {c["id"] for c in P.CHECKS}


def test_a_common_condition_is_demoted_from_flag_to_base_condition():
    """The rule the whole panel turns on: a condition true of a third of the
    universe describes the market, not this company."""
    cal = calibration(altmanDistress=P.BASE_RATE_MAX + 0.05)
    result = assess(payload(quality=quality(altman="distress")), cal)
    assert "altmanDistress" not in fired_ids(result)
    base = [b["id"] for b in result["baseConditions"]]
    assert base == ["altmanDistress"]
    # Demoted means uncoloured. A base rate rendered in warning colours is the
    # exact confusion the demotion exists to prevent.
    assert result["baseConditions"][0]["explain"]["band"] == "context"
    assert result["baseConditions"][0]["explain"]["tone"] == "neutral"


def test_a_rare_condition_stays_a_flag_and_keeps_its_colour():
    cal = calibration(altmanDistress=0.02)
    result = assess(payload(quality=quality(altman="distress")), cal)
    assert fired_ids(result) == ["altmanDistress"]
    assert result["flags"][0]["explain"]["band"] == "bad"


def test_every_rendered_check_carries_its_own_firing_rate():
    result = assess(payload(
        quality=quality(altman="distress", beneish="flagged"),
        technical=technical(hurst="indistinguishable"),
    ))
    assert result["flags"]
    for entry in result["flags"] + result["baseConditions"]:
        assert 0.0 <= entry["firingRate"] <= 1.0
        assert entry["firingRateText"].endswith("%")
        assert "fires on" in entry["rateSentence"].lower()
        assert entry["universeLabel"]


# --------------------------------------------------------------------------- #
# 4b. The rate has to describe the market the reader is looking at
# --------------------------------------------------------------------------- #
# The full calibration run is what forced this: "scores built from incomplete
# data" fires on 10% of the Dow and 80% of IDX30, because Yahoo's coverage of
# smaller Indonesian filings is thin. The blend near 40% is simultaneously
# alarming for a US large cap and reassuring for an IDX one, and neither reading
# is true of the company in front of the reader.
THIN_BY_MARKET = {"thinFilings": {
    "US": {"firingRate": 0.13, "sampleSize": 128, "couldNotRun": 5},
    "ID": {"firingRate": 0.82, "sampleSize": 75, "couldNotRun": 0},
}}


def test_the_market_specific_rate_wins_over_the_blended_one():
    cal = calibration(thinFilings=0.40, markets=THIN_BY_MARKET)
    thin = payload(quality=quality(indices_available=6))

    us = assess(thin, cal, market="US")
    assert [f["id"] for f in us["flags"]] == ["thinFilings"], "rare in the US: a flag"
    assert us["flags"][0]["firingRateText"] == "13%"
    assert "the Dow and the Nasdaq-100" in us["flags"][0]["rateSentence"]

    idx = assess(thin, cal, market="ID")
    assert [b["id"] for b in idx["baseConditions"]] == ["thinFilings"], \
        "the norm on the IDX: a base condition, not an alarm"
    assert idx["baseConditions"][0]["firingRateText"] == "82%"
    assert "IDX30 and LQ45" in idx["baseConditions"][0]["rateSentence"]

    # And the blend, which is what a market-blind panel would have shown, is the
    # one answer that is wrong for both.
    assert assess(thin, cal)["baseConditions"][0]["firingRateText"] == "40%"


def test_an_uncalibrated_market_falls_back_to_the_combined_rate():
    """A market nobody measured is not a reason to withhold a check that WAS
    measured — it is a reason to say which group the percentage describes."""
    cal = calibration(thinFilings=0.11, markets=THIN_BY_MARKET)
    result = assess(payload(quality=quality(indices_available=6)), cal, market="XX")
    entry = result["flags"][0]
    assert entry["firingRateText"] == "11%"
    assert "four index universes" in entry["rateSentence"]


def test_a_thin_market_sample_falls_back_rather_than_quoting_noise():
    cal = calibration(thinFilings=0.11, markets={"thinFilings": {
        "ID": {"firingRate": 0.9, "sampleSize": P.MIN_CALIBRATION_SAMPLE - 1,
               "couldNotRun": 0}}})
    entry = assess(payload(quality=quality(indices_available=6)), cal,
                   market="ID")["flags"][0]
    assert entry["firingRateText"] == "11%", "quoted a rate from too few names"


def test_the_calibration_date_is_carried_because_membership_decays():
    result = assess()
    assert result["calibration"]["measuredOn"] == "2026-08-28"
    assert "2026-08-28" in result["measuredOn"]


def test_no_calibration_at_all_renders_nothing_and_says_why():
    result = P.assess(payload(quality=quality(altman="distress")), calibration=None)
    assert result["flags"] == [] and result["baseConditions"] == []
    assert result["calibration"] is None
    assert len(result["uncalibrated"]) == len(P.CHECKS)


# --------------------------------------------------------------------------- #
# 5. The checks themselves fire on what they claim to
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pl,expected", [
    ({"quality": quality(altman="distress")}, "altmanDistress"),
    ({"quality": quality(beneish="flagged", beneish_score=-1.2)}, "beneishFlagged"),
    ({"quality": quality(piotroski_band="weak", score=2)}, "piotroskiWeak"),
    ({"valuation": valuation(terminal=0.74)}, "terminalDominant"),
    ({"valuation": valuation(implied=0.31, assumed=0.10)}, "impliedGrowthDemanding"),
    ({"quality": quality(indices_available=6)}, "thinFilings"),
    ({"valuation": valuation(manual={"base": True})}, "thinFilings"),
    ({"technical": technical(hurst="indistinguishable", hurst_value=0.51)}, "hurstRandomWalk"),
    ({"anomaly": anomaly(inside=True, ratio=1.4)}, "moveInsideCost"),
    ({"technical": technical(max_dd=-0.63)}, "deepDrawdownHistory"),
])
def test_each_check_fires_on_its_own_condition_and_only_then(pl, expected):
    assert expected in fired_ids(assess(payload(**pl)))
    assert expected not in fired_ids(assess()), f"{expected} fired on a clean payload"


def test_a_fired_check_quotes_the_number_it_fired_on():
    """A flag a reader cannot check is one they have to take on trust."""
    result = assess(payload(technical=technical(max_dd=-0.63)))
    entry = next(f for f in result["flags"] if f["id"] == "deepDrawdownHistory")
    assert "63%" in entry["explain"]["reading"]
    assert entry["where"], "a check must name the panel that owns its number"


def test_the_implied_growth_gap_is_measured_against_the_assumption_not_a_constant():
    """A high implied growth that MATCHES the model's own assumption is not a
    disagreement, and firing on it would flag every high-growth company."""
    assert "impliedGrowthDemanding" not in fired_ids(
        assess(payload(valuation=valuation(implied=0.30, assumed=0.30))))
    assert "impliedGrowthDemanding" in fired_ids(
        assess(payload(valuation=valuation(implied=0.30, assumed=0.10))))


# --------------------------------------------------------------------------- #
# 6. It never instructs, and it never falls over
# --------------------------------------------------------------------------- #
FORBIDDEN = [
    "you should buy", "you should sell", "we recommend", "do not buy", "avoid this",
    "strong buy", "buy now", "sell now", "buy signal", "sell signal",
    "price target of", "guaranteed", "will rise", "will fall", "safe to buy",
]


@pytest.mark.parametrize("altman", ["safe", "distress"])
@pytest.mark.parametrize("beneish", ["clean", "flagged"])
@pytest.mark.parametrize("hurst", ["persistent", "indistinguishable"])
def test_no_combination_ever_produces_an_instruction(altman, beneish, hurst):
    text = all_text(assess(payload(
        quality=quality(altman=altman, beneish=beneish),
        technical=technical(hurst=hurst))))
    for phrase in FORBIDDEN:
        assert phrase not in text, f"pre-trade panel said {phrase!r}"


@pytest.mark.parametrize("pl", [
    {}, {"quality": leg({})}, {"technical": leg({"longTerm": None})},
    {"valuation": leg({"baseCase": "not a dict"})},
    {"anomaly": {"ok": True, "data": None}},
    {"technical": "not a dict"},
    {"quality": leg({"applicable": True, "altman": None, "beneish": None,
                     "piotroski": None})},
])
def test_degenerate_payloads_never_raise(pl):
    """Every engine can return a shape nobody expected. The panel whose job is to
    say what could not be checked must not be the one that 500s."""
    result = P.assess(pl, calibration())
    assert isinstance(result["headline"], str) and result["caveat"]
    assert isinstance(result["flags"], list)


def test_a_raising_check_becomes_not_checked_rather_than_clear(monkeypatch):
    def explode(_payload):
        raise ValueError("engine returned something unexpected")

    monkeypatch.setitem(P.CHECK_BY_ID["altmanDistress"], "fn", explode)
    monkeypatch.setattr(P, "CHECKS", [P.CHECK_BY_ID["altmanDistress"]])
    result = P.assess(payload(), calibration(only=["altmanDistress"]))
    assert [n["id"] for n in result["notChecked"]] == ["altmanDistress"]
    assert result["flags"] == []


# --------------------------------------------------------------------------- #
# 7. The registry stays coherent
# --------------------------------------------------------------------------- #
def test_every_check_is_fully_declared():
    ids = set()
    for check in P.CHECKS:
        for field in ("id", "label", "family", "where", "evidence", "what", "action", "fn"):
            assert check.get(field), f"{check.get('id')} is missing {field}"
        assert check["family"] in ("price", "filings")
        assert check["evidence"] in E.EVIDENCE
        assert check["id"] not in ids, f"duplicate check id {check['id']}"
        ids.add(check["id"])


def test_the_notes_are_keyed_by_section_and_only_present_when_that_section_is():
    """The panel places each note under the section it describes. Keys are the
    contract; matching on wording would drop a note the moment it was reworded."""
    assert P.assess(payload(), calibration())["notes"] == {}, \
        "a clean payload has no sections, so it has no section notes"

    full = P.assess(
        payload(quality=quality(applicable=False), technical=technical(has_long=False)),
        calibration(only=["altmanDistress", "beneishFlagged", "piotroskiWeak",
                          "hurstRandomWalk", "deepDrawdownHistory"]))
    assert set(full["notes"]) == {"notChecked", "uncalibrated"}, full["notes"]

    demoted = P.assess(payload(quality=quality(altman="distress")),
                       calibration(altmanDistress=P.BASE_RATE_MAX + 0.1))
    assert "base" in demoted["notes"]


def test_the_shipped_calibration_covers_every_check_or_the_panel_says_so():
    """A shipped file that has silently fallen behind the registry is the failure
    this catches — the panel degrades correctly either way, but it should not do
    so unnoticed."""
    shipped = P.load_calibration()
    if shipped is None:
        pytest.skip("no calibration measured yet; scripts/calibrate_checks.py writes it")
    missing = [c["id"] for c in P.CHECKS if c["id"] not in shipped["checks"]]
    assert not missing, (f"{missing} have no measured firing rate. Re-run "
                         f"scripts/calibrate_checks.py after changing the registry.")
    # Both markets the app covers must be represented, or half the readers get a
    # rate measured on the other half's companies.
    assert set(shipped.get("marketLabels") or {}) >= {"US", "ID"}
    for check in P.CHECKS:
        entry = shipped["checks"][check["id"]]
        assert set(entry.get("markets") or {}) >= {"US", "ID"}, check["id"]
