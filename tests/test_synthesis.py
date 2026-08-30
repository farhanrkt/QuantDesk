"""The cross-lens synthesis.

The thing under test is PROSE, so the assertions are about what the prose
commits to rather than its wording: that a disagreement is named as a
disagreement, that a limit in force is stated, that a failed leg degrades into a
blind spot rather than an exception, and above all that no combination of inputs
ever produces a buy/sell instruction. Wording is free to change; those four
guarantees are not.
"""

from __future__ import annotations

import pytest

from _lib import explain as E


def leg(data, ok=True, error=None):
    return {"ok": ok, "data": data} if ok else {"ok": False, "error": error}


def flow(recent=0, days=10, bias="Neutral", total=5, spread_resolved=True, current=None):
    return leg({
        "stats": {"recentCount": recent, "recentDays": days, "recentFlowBias": bias,
                  "anomalyCount": total},
        "liquidity": {"spreadResolved": spread_resolved},
        "accumulation": {"current": current},
    })


def trend(verdict="CONSTRUCTIVE", tone="bull", hurst="trending", has_long=True,
          max_dd=-0.33):
    return leg({
        "hasLongTerm": has_long,
        "summary": {"trend": "Sideways", "trend_tone": "neutral",
                    "headline": "**X** is in a **sideways** trend. More text."},
        "longTerm": {
            "view": {"verdict": verdict, "tone": tone, "passed": 6, "scored": 8,
                     "headline": "The long-horizon evidence mostly points upward."},
            "hurstReading": {"verdict": hurst},
            "drawdown": {"maxDrawdown": max_dd},
        },
    })


def value(verdict="UNDERVALUED", upside=0.30, terminal=0.35):
    return leg({
        "verdict": verdict, "engine": "DCF",
        "monteCarlo": {"p50Label": "$120.00", "upside": upside, "probUndervalued": 0.8},
        "baseCase": {"terminalShare": terminal},
    })


def quality(verdict="SOUND", applicable=True, beneish="clean", altman="safe", score=8):
    if not applicable:
        return leg({"applicable": False})
    return leg({"applicable": True, "verdict": verdict,
                "piotroski": {"score": score, "maxScore": 9},
                "altman": {"band": altman}, "beneish": {"band": beneish}})


def build(measured=None, **kw):
    """The synthesis, with NO agreement measurement unless a test supplies one.

    Passed explicitly rather than left to the default, which would read
    `lens_agreement.json` off disk — and a suite whose assertions depended on
    whether a research script had been re-run would be a suite that failed for
    reasons unrelated to the code under test. The measured branches get their
    own tests below, with a planted measurement.
    """
    payload = {"anomaly": flow(), "technical": trend(), "valuation": value(),
               "quality": quality()}
    payload.update(kw)
    return E.for_synthesis(payload, agreement_measurement=measured)


def all_text(s) -> str:
    """Every sentence the synthesis would put on screen, as one blob."""
    parts = [s["headline"], s["caveat"], s["agreement"]["text"]]
    parts += [r["sentence"] for r in s["readings"]]
    parts += [t["title"] + " " + t["text"] for t in s["tensions"]]
    parts += [b["title"] + " " + b["text"] for b in s["blindSpots"]]
    parts += list(s["nextChecks"])
    return " ".join(parts).lower()


# --------------------------------------------------------------------------- #
# The guarantee that matters most
# --------------------------------------------------------------------------- #
FORBIDDEN = [
    "you should buy", "you should sell", "we recommend", "recommended buy",
    "strong buy", "buy now", "sell now", "buy signal", "sell signal",
    "price target of", "guaranteed", "will rise", "will fall",
]


@pytest.mark.parametrize("verdict", ["UNDERVALUED", "FAIR", "OVERVALUED"])
@pytest.mark.parametrize("tone", ["bull", "bear", "neutral"])
@pytest.mark.parametrize("q", ["SOUND", "CONCERNS", "NEUTRAL"])
def test_no_combination_ever_produces_an_instruction(verdict, tone, q):
    """27 permutations of the four lenses, and none may tell anyone to trade.

    This is the feature's whole contract. A synthesis that starts recommending
    under some rare combination of inputs is worse than no synthesis, because
    the combination that trips it will not be the one anybody tested by hand.
    """
    text = all_text(build(valuation=value(verdict=verdict),
                          technical=trend(tone=tone),
                          quality=quality(verdict=q)))
    for phrase in FORBIDDEN:
        assert phrase not in text, f"synthesis said {phrase!r}"


def test_the_caveat_is_always_present_and_says_it_is_not_advice():
    s = build()
    assert "not a recommendation" in s["caveat"]
    assert "forecast" in s["caveat"]


# --------------------------------------------------------------------------- #
# Agreement is counted in SOURCES, not panels
# --------------------------------------------------------------------------- #
def test_four_agreeing_lenses_report_two_independent_sources():
    s = build(technical=trend(tone="bull"), valuation=value(verdict="UNDERVALUED"),
              quality=quality(verdict="SOUND"), anomaly=flow(recent=3, bias="Accumulation"))
    assert s["agreement"]["lensesReading"] == 4
    assert s["agreement"]["independentSources"] == 2, "four panels are not four opinions"
    assert s["agreement"]["tone"] == "good"
    # With no measurement in hand the warrant is stated as an assumption and
    # says so. The three measured branches are asserted below.
    assert "read different data" in s["agreement"]["text"]
    assert "stated assumption" in s["agreement"]["text"]
    assert "measured" not in s["agreement"]


# --------------------------------------------------------------------------- #
# The warrant — the clause that says WHY agreement is worth anything
#
# Three branches, and all three have to ship. The claim "agreement between them
# is not one fact counted twice" was an assertion for the whole life of this app
# until §15 measured it, and a module that could only phrase the result it hoped
# for would have decided the answer before the run. So each branch is exercised
# with a planted measurement, and the guarantee that matters most — that no
# combination ever produces an instruction — is asserted across all of them.
# --------------------------------------------------------------------------- #
def measured(kappa: float, excludes_zero: bool, n: int = 141) -> dict:
    """A stamped agreement measurement in the shape `_warrant` reads."""
    return {"measuredOn": "2026-08-29", "scope": "the Dow 30 and the Nasdaq-100",
            "families": {"kappa": kappa, "n": n, "observed": 0.44, "chance": 0.41,
                         "excludesZero": excludes_zero, "usable": True},
            "pairs": [], "lenses": {"available": False},
            "reading": "a planted measurement"}


def agreeing(**kw):
    return build(technical=trend(tone="bull"), valuation=value(verdict="UNDERVALUED"),
                 quality=quality(verdict="SOUND"),
                 anomaly=flow(recent=3, bias="Accumulation"), **kw)


def test_a_null_agreement_measurement_earns_the_claim_rather_than_assuming_it():
    s = agreeing(measured=measured(0.03, excludes_zero=False))
    text = s["agreement"]["text"]
    assert "measured rather than assumed" in text
    assert "two facts and not one counted twice" in text
    assert "141 names in the Dow 30 and the Nasdaq-100" in text
    assert s["agreement"]["measured"]["families"]["kappa"] == 0.03


def test_a_redundant_measurement_takes_the_claim_away():
    """The branch that had to exist for the measurement to mean anything. If the
    two families agree well beyond chance, "the strongest thing this app can
    say" is overstating it, and the sentence has to concede that rather than
    carrying on beside a number that contradicts it."""
    s = agreeing(measured=measured(0.52, excludes_zero=True))
    text = s["agreement"]["text"]
    assert "worth less than two independent readings" in text
    assert "not one fact counted twice" not in text
    assert "measured rather than assumed" not in text


def test_below_chance_agreement_is_reported_as_the_oddity_it_is():
    s = agreeing(measured=measured(-0.28, excludes_zero=True))
    assert "agree LESS often than chance" in s["agreement"]["text"]
    assert "reassurance" in s["agreement"]["text"]


@pytest.mark.parametrize("m", [None, measured(0.03, False), measured(0.52, True),
                               measured(-0.28, True)])
def test_no_warrant_branch_ever_produces_an_instruction(m):
    """The guarantee that outranks everything else in this file, checked against
    every way the warrant can now be phrased."""
    text = all_text(agreeing(measured=m))
    for phrase in FORBIDDEN:
        assert phrase not in text, f"the {'measured' if m else 'assumed'} warrant said {phrase!r}"


def test_the_measurement_is_carried_but_never_consumed():
    """It rides beside the sentence it justifies and nothing else reads it. A
    measured agreement that started scaling a verdict would be the composite
    score this app refuses to have, arrived at through a Greek letter."""
    high = agreeing(measured=measured(0.52, excludes_zero=True))
    low = agreeing(measured=measured(0.03, excludes_zero=False))
    for key in ("tone", "independentSources", "lensesReading"):
        assert high["agreement"][key] == low["agreement"][key]
    assert high["headline"] == low["headline"]
    assert [r["vote"] for r in high["readings"]] == [r["vote"] for r in low["readings"]]


def test_an_unmeasured_run_carries_no_measurement_key_at_all():
    assert "measured" not in agreeing(measured=None)["agreement"]


def test_a_price_filings_disagreement_is_named_as_the_finding():
    s = build(technical=trend(tone="bull"), anomaly=flow(recent=2, bias="Accumulation"),
              valuation=value(verdict="OVERVALUED", upside=-0.4),
              quality=quality(verdict="CONCERNS"))
    assert s["agreement"]["tone"] == "warn"
    assert "disagree" in s["agreement"]["text"]
    assert "the disagreement is the finding" in s["agreement"]["text"].lower()


def test_one_family_alone_is_reported_as_having_no_cross_check():
    s = E.for_synthesis({"valuation": value(), "quality": quality()},
                        agreement_measurement=None)
    assert s["agreement"]["independentSources"] == 1
    assert "no cross-check" in s["agreement"]["text"]


def test_a_split_inside_one_family_is_named():
    """Flow and Trend read the same data. Pointing opposite ways is a finding."""
    s = build(anomaly=flow(recent=4, bias="Distribution"), technical=trend(tone="bull"))
    titles = [t["title"] for t in s["tensions"]]
    assert any("Split within price and volume" in t for t in titles), titles


# --------------------------------------------------------------------------- #
# The gap is quoted against the thing the sentence names
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("p50", "price", "expected"),
    [
        # ITMG.JK, live: the sentence used to read "159% below that", which is
        # `upside` — a fraction of the PRICE — printed against the fair value.
        # Nothing can be more than 100% below anything.
        (66_540.0, 25_650.0, "61% below that"),
        (112.40, 314.58, "180% above that"),   # AAPL: was reported as 64%
        (120.0, 100.0, "17% below that"),      # +20% upside is -16.7% from fair
        (100.0, 100.0, "0% below that"),       # exactly on it
    ],
)
def test_the_gap_is_measured_against_the_fair_value_it_names(p50, price, expected):
    payload = {
        "verdict": "UNDERVALUED", "engine": "DCF", "price": price,
        "monteCarlo": {"p50Label": "x", "p50": p50,
                       "upside": (p50 - price) / price, "probUndervalued": 0.8},
        "baseCase": {"terminalShare": 0.35},
    }
    reading = next(r for r in E.for_synthesis(
        {"valuation": leg(payload)}, agreement_measurement=None)["readings"]
        if r["lens"] == "Value")
    assert expected in reading["sentence"], reading["sentence"]
    # A share price cannot be more than all of itself below something.
    if "below" in reading["sentence"]:
        percent = int(reading["sentence"].split("% below")[0].split()[-1])
        assert percent <= 100, reading["sentence"]


# --------------------------------------------------------------------------- #
# Named tensions
# --------------------------------------------------------------------------- #
def test_cheap_plus_flagged_accounts_is_called_a_value_trap_shape():
    s = build(valuation=value(verdict="UNDERVALUED"),
              quality=quality(verdict="CONCERNS", beneish="flagged"))
    tension = next((t for t in s["tensions"] if "flagged" in t["title"].lower()), None)
    assert tension is not None, [t["title"] for t in s["tensions"]]
    assert "value trap" in tension["text"]
    # And it must say WHY the two are not independent evidence here.
    assert "same statements" in tension["text"]


def test_rising_past_the_business_is_named_when_trend_and_value_conflict():
    s = build(technical=trend(tone="bull"), valuation=value(verdict="OVERVALUED"))
    assert any("supports" in t["title"] for t in s["tensions"])


# --------------------------------------------------------------------------- #
# Blind spots are switched on by real numbers, not printed always
# --------------------------------------------------------------------------- #
def test_a_random_walk_verdict_downgrades_the_price_lenses():
    s = build(technical=trend(hurst="indistinguishable"))
    spot = next((b for b in s["blindSpots"] if "noise" in b["title"]), None)
    assert spot is not None
    # The guarantee is that the blind spot tells the reader to discount the
    # price lenses, not the verb it uses. Wording shortened in the v2 copy pass.
    assert "discount" in spot["text"]
    # Clean case must NOT print it.
    assert not any("noise" in b["title"] for b in build()["blindSpots"])


def test_a_terminal_heavy_valuation_says_so_with_its_own_number():
    s = build(valuation=value(terminal=0.74))
    spot = next((b for b in s["blindSpots"] if "perpetuity" in b["title"]), None)
    assert spot is not None and "74%" in spot["text"]
    assert not any("perpetuity" in b["title"] for b in build(valuation=value(terminal=0.2))["blindSpots"])


def test_an_unresolved_spread_is_reported_as_a_ceiling():
    s = build(anomaly=flow(spread_resolved=False))
    assert any("ceiling" in b["title"] for b in s["blindSpots"])


def test_a_bank_gets_a_refusal_and_a_stated_loss_of_evidence():
    s = build(quality=quality(applicable=False))
    reading = next(r for r in s["readings"] if r["lens"] == "Quality")
    assert reading["tone"] == "none"
    assert "refusal" in reading["sentence"]
    assert any("accounting screen" in b["title"] for b in s["blindSpots"])
    # A refused lens must not be counted as a reading.
    assert s["agreement"]["lensesReading"] == 3


# --------------------------------------------------------------------------- #
# Degradation
# --------------------------------------------------------------------------- #
def test_a_failed_leg_becomes_a_blind_spot_not_an_exception():
    s = build(valuation=leg(None, ok=False, error="No usable market data."))
    assert any("Value did not run" in b["title"] for b in s["blindSpots"])
    assert all(r["lens"] != "Value" for r in s["readings"])


def test_a_structured_error_detail_is_flattened_rather_than_dumped():
    s = build(valuation=leg(None, ok=False,
                            error={"manualRequired": True, "message": "Yahoo has no price."}))
    spot = next(b for b in s["blindSpots"] if "Value did not run" in b["title"])
    assert "Yahoo has no price." in spot["text"]
    assert "manualRequired" not in spot["text"]


@pytest.mark.parametrize("payload", [
    {}, {"anomaly": leg({})}, {"technical": leg({"summary": {}})},
    {"valuation": leg({"verdict": None, "monteCarlo": {}})},
    {"quality": leg({"applicable": True})},
    {"anomaly": {"ok": True, "data": None}},
    {"technical": "not a dict"},
])
def test_degenerate_payloads_never_raise(payload):
    """Every engine can return a shape nobody expected. The panel whose job is
    to explain the others must not be the one that 500s."""
    s = E.for_synthesis(payload, agreement_measurement=None)
    assert isinstance(s["headline"], str) and s["caveat"]


def test_nothing_usable_says_so_plainly():
    s = E.for_synthesis({}, agreement_measurement=None)
    assert "no lens" in s["headline"].lower()
    assert s["agreement"]["independentSources"] == 0
