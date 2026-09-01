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


def expectations(verdict="MIXED", applicable=True, up=5, down=4, moves=9,
                 analysts=20, growth=None, drift_change=None):
    if not applicable:
        return leg({"applicable": False, "analysts": analysts})
    return leg({
        "applicable": True, "analysts": analysts, "verdict": verdict,
        "headline": "planted",
        "breadth": {"available": True, "up": up, "down": down, "moves": moves,
                    "diffusion": (up - down) / moves if moves else None,
                    "state": verdict.lower()},
        "drift": {"annual90": {"available": True, "days": 90,
                               "state": "moved" if drift_change else "flat",
                               "change": drift_change if drift_change else 0.001}},
        "consensusGrowth": ({"available": True, "nextYear": growth,
                             "horizon": "one fiscal year"}
                            if growth is not None else {"available": False}),
    })


def build(measured=None, **kw):
    """The synthesis, with NO agreement measurement unless a test supplies one.

    Passed explicitly rather than left to the default, which would read
    `lens_agreement.json` off disk — and a suite whose assertions depended on
    whether a research script had been re-run would be a suite that failed for
    reasons unrelated to the code under test. The measured branches get their
    own tests below, with a planted measurement.
    """
    payload = {"anomaly": flow(), "technical": trend(), "valuation": value(),
               "quality": quality(), "expectations": expectations()}
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
def test_five_agreeing_lenses_report_three_independent_sources():
    s = build(technical=trend(tone="bull"), valuation=value(verdict="UNDERVALUED"),
              quality=quality(verdict="SOUND"), anomaly=flow(recent=3, bias="Accumulation"),
              expectations=expectations(verdict="RISING", up=9, down=2, moves=11))
    assert s["agreement"]["lensesReading"] == 5
    assert s["agreement"]["independentSources"] == 3, "five panels are not five opinions"
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
    governing = {"a": "price and volume", "b": "the filings",
                 "kappa": kappa, "n": n, "observed": 0.44, "chance": 0.41,
                 "excludesZero": excludes_zero, "usable": True}
    return {"measuredOn": "2026-08-29", "scope": "the Dow 30 and the Nasdaq-100",
            "families": governing,
            # Three pairs now, of which `families` is the most redundant. The
            # warrant speaks about that one and names it.
            "familyPairs": [governing,
                            {**governing, "a": "price and volume",
                             "b": "the estimate record", "kappa": kappa - 0.05},
                            {**governing, "a": "the filings",
                             "b": "the estimate record", "kappa": kappa - 0.02}],
            "pairs": [], "lenses": {"available": False},
            "reading": "a planted measurement"}


def agreeing(**kw):
    return build(technical=trend(tone="bull"), valuation=value(verdict="UNDERVALUED"),
                 quality=quality(verdict="SOUND"),
                 anomaly=flow(recent=3, bias="Accumulation"),
                 expectations=expectations(verdict="RISING", up=9, down=2, moves=11),
                 **kw)


def test_a_null_agreement_measurement_earns_the_claim_rather_than_assuming_it():
    s = agreeing(measured=measured(0.03, excludes_zero=False))
    text = s["agreement"]["text"]
    assert "measured rather than assumed" in text
    # "separate facts" rather than "two facts": with three families the warrant
    # names the most redundant PAIR and speaks about the set, so a hardcoded
    # "two" would have been wrong the moment a third family arrived.
    assert "separate facts and not one counted twice" in text
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
    # A refused lens must not be counted as a reading. Four of five remain.
    assert s["agreement"]["lensesReading"] == 4


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


# --------------------------------------------------------------------------- #
# Three families — the generalisation §18 required
#
# `_agreement` read `families["price"]` and `families["filings"]` by name, so a
# third family would have raised a KeyError on the busiest route in the app —
# or, worse, been "fixed" by dropping the third from the sentence while
# `independentSources` went on counting it. These hold the generalisation.
# --------------------------------------------------------------------------- #
def test_two_of_three_agreeing_is_not_reported_as_all_three():
    """A materially weaker claim than unanimity, and it must read as one."""
    s = build(anomaly=flow(recent=3, bias="Accumulation"), technical=trend(tone="bull"),
              valuation=value(verdict="UNDERVALUED"), quality=quality(verdict="SOUND"),
              expectations=expectations(verdict="MIXED"),
              measured=measured(0.03, excludes_zero=False))
    text = s["agreement"]["text"]
    assert s["agreement"]["independentSources"] == 3
    assert "2 of the 3 bodies of data" in text
    assert "All three" not in text


def test_all_three_agreeing_says_all_three():
    s = agreeing(measured=measured(0.03, excludes_zero=False))
    assert "All three bodies of data" in s["agreement"]["text"]
    assert s["agreement"]["tone"] == "good"


def test_a_disagreement_names_every_family_on_each_side():
    """With three families the two sides are lists, not a pair of nouns."""
    s = build(anomaly=flow(recent=3, bias="Accumulation"), technical=trend(tone="bull"),
              valuation=value(verdict="OVERVALUED"), quality=quality(verdict="CONCERNS"),
              expectations=expectations(verdict="FALLING", up=1, down=9, moves=10))
    text = s["agreement"]["text"]
    assert s["agreement"]["tone"] == "warn"
    assert "price and volume" in text
    assert "the filings" in text and "the estimate record" in text
    assert "disagreement is the finding" in text


def test_every_family_neutral_is_its_own_reported_state():
    s = build(anomaly=flow(), technical=trend(tone="neutral"),
              valuation=value(verdict="FAIRLY VALUED"), quality=quality(verdict="NEUTRAL"),
              expectations=expectations(verdict="MIXED"))
    assert s["agreement"]["tone"] == "neutral"
    assert "every one of them came out neutral" in s["agreement"]["text"]


def test_the_warrant_names_the_governing_pair():
    """With three pairs, "the two" is ambiguous — the sentence has to say which."""
    s = agreeing(measured=measured(0.30, excludes_zero=True))
    text = s["agreement"]["text"]
    assert "price and volume" in text and "the filings" in text
    assert "worth less than two independent readings" in text


def test_an_uncovered_listing_does_not_vote_and_leaves_two_sources():
    """The refusal is not a neutral vote. It removes the family entirely."""
    s = build(expectations=expectations(applicable=False, analysts=1))
    reading = next(r for r in s["readings"] if r["lens"] == "Expectations")
    assert reading["tone"] == "none"
    assert reading["vote"] == 0
    assert s["agreement"]["independentSources"] == 2


def test_a_quiet_estimate_record_is_a_reading_that_votes_zero():
    """Opposite finding from the refusal above, and it must not render alike."""
    s = build(expectations=expectations(verdict="QUIET", up=0, down=0, moves=0))
    reading = next(r for r in s["readings"] if r["lens"] == "Expectations")
    assert reading["tone"] == "neutral"
    assert reading["vote"] == 0
    # It still counts as a source, because the lens genuinely read something.
    assert s["agreement"]["independentSources"] == 3
    assert any("nothing to add" in b["title"] for b in s["blindSpots"])


def test_an_uncovered_listing_is_named_as_a_blind_spot():
    s = build(expectations=expectations(applicable=False, analysts=0))
    assert any("Nobody publishes estimates" in b["title"] for b in s["blindSpots"])


# --------------------------------------------------------------------------- #
# The tensions the fifth lens makes possible
# --------------------------------------------------------------------------- #
def test_cheap_with_falling_forecasts_is_named_as_the_trap_shape():
    """The gap the four lenses could not see: a DCF reads last year's filings,
    and the consensus is the more current record."""
    s = build(valuation=value(verdict="UNDERVALUED"),
              expectations=expectations(verdict="FALLING", up=1, down=9, moves=10))
    titles = [t["title"] for t in s["tensions"]]
    assert "Cheap, and the forecasts are still coming down" in titles


def test_expensive_with_rising_forecasts_refuses_to_settle_which_is_right():
    s = build(valuation=value(verdict="OVERVALUED"),
              expectations=expectations(verdict="RISING", up=9, down=1, moves=10))
    tension = next(t for t in s["tensions"]
                   if t["title"] == "Expensive, with the forecasts being raised")
    assert "cannot tell you which" in tension["text"]


def test_flagged_accounts_with_rising_forecasts_says_they_are_not_independent():
    """Analysts forecast FROM the statements the screens are questioning."""
    s = build(quality=quality(verdict="CONCERNS", beneish="flagged"),
              expectations=expectations(verdict="RISING", up=9, down=1, moves=10))
    tension = next(t for t in s["tensions"]
                   if t["title"] == "The accounts are flagged, the forecasts are not")
    assert "not two" in tension["text"]


def test_the_implied_growth_gap_is_named_only_when_it_is_large():
    """The comparison crosses horizons — five forecast years against one fiscal
    year — so a few points could be nothing but that mismatch."""
    wide = build(valuation=leg({"verdict": "OVERVALUED", "engine": "DCF",
                                "monteCarlo": {"p50Label": "$80", "upside": -0.2,
                                               "probUndervalued": 0.2},
                                "baseCase": {"terminalShare": 0.4,
                                             "impliedGrowth": 0.25}}),
                 expectations=expectations(growth=0.05))
    assert any("needs more growth than anyone forecasts" in t["title"]
               for t in wide["tensions"])

    narrow = build(valuation=leg({"verdict": "OVERVALUED", "engine": "DCF",
                                  "monteCarlo": {"p50Label": "$80", "upside": -0.2,
                                                 "probUndervalued": 0.2},
                                  "baseCase": {"terminalShare": 0.4,
                                               "impliedGrowth": 0.09}}),
                   expectations=expectations(growth=0.05))
    assert not any("needs more growth than anyone forecasts" in t["title"]
                   for t in narrow["tensions"])


def test_the_growth_gap_states_that_the_horizons_differ():
    """Stretching a one-year consensus silently to five would be the worse error."""
    s = build(valuation=leg({"verdict": "OVERVALUED", "engine": "DCF",
                             "monteCarlo": {"p50Label": "$80", "upside": -0.2,
                                            "probUndervalued": 0.2},
                             "baseCase": {"terminalShare": 0.4, "impliedGrowth": 0.25}}),
              expectations=expectations(growth=0.05))
    tension = next(t for t in s["tensions"]
                   if "needs more growth" in t["title"])
    assert "horizons are not the same" in tension["text"]
    assert "not a verdict" in tension["text"]


@pytest.mark.parametrize("verdict", ["RISING", "FALLING", "MIXED", "QUIET", "THIN"])
def test_no_expectations_verdict_ever_produces_an_instruction(verdict):
    s = build(expectations=expectations(verdict=verdict))
    text = all_text(s)
    for banned in ("you should buy", "you should sell", "we recommend", "strong buy"):
        assert banned not in text
