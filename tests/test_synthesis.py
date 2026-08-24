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


def build(**kw):
    payload = {"anomaly": flow(), "technical": trend(), "valuation": value(),
               "quality": quality()}
    payload.update(kw)
    return E.for_synthesis(payload)


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
    assert "share no inputs" in s["agreement"]["text"]


def test_a_price_filings_disagreement_is_named_as_the_finding():
    s = build(technical=trend(tone="bull"), anomaly=flow(recent=2, bias="Accumulation"),
              valuation=value(verdict="OVERVALUED", upside=-0.4),
              quality=quality(verdict="CONCERNS"))
    assert s["agreement"]["tone"] == "warn"
    assert "disagree" in s["agreement"]["text"]
    assert "the disagreement is the finding" in s["agreement"]["text"].lower()


def test_one_family_alone_is_reported_as_having_no_cross_check():
    s = E.for_synthesis({"valuation": value(), "quality": quality()})
    assert s["agreement"]["independentSources"] == 1
    assert "no cross-check" in s["agreement"]["text"]


def test_a_split_inside_one_family_is_named():
    """Flow and Trend read the same data. Pointing opposite ways is a finding."""
    s = build(anomaly=flow(recent=4, bias="Distribution"), technical=trend(tone="bull"))
    titles = [t["title"] for t in s["tensions"]]
    assert any("Split within price and volume" in t for t in titles), titles


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
    assert "downgrade" in spot["text"]
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
    s = E.for_synthesis(payload)
    assert isinstance(s["headline"], str) and s["caveat"]


def test_nothing_usable_says_so_plainly():
    s = E.for_synthesis({})
    assert "no lens" in s["headline"].lower()
    assert s["agreement"]["independentSources"] == 0
