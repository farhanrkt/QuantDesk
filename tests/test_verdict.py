"""The private scanner's score, action and gates.

WHAT THESE TESTS PROTECT, IN ORDER OF HOW BADLY IT WOULD HURT TO LOSE IT

1. THE PUBLISHED SURFACES STAY CLEAN. `verdict.py` produces exactly the
   composite `PRODUCT.md` constraint 1 refuses for the single-company view, and
   the only thing keeping that refusal true is that nothing on that path imports
   this module. That is asserted here rather than trusted, because it is a
   one-line mistake to make and nothing else would catch it.

2. NOTHING IS EVER IMPUTED. A lens that did not return removes its weight from
   the blend; it never contributes a 50. The difference is invisible in the
   output — both produce a score — and it is the difference between a
   measurement and a guess.

3. A REFUSAL IS NOT A GAP. Quality on a bank comes back `refused`, not
   `unavailable`, and never as a low score. IDX is roughly a third banks by
   index weight, so getting this wrong would systematically mark down the
   largest names in the market for a screen that was never applicable to them.

4. GATES OVERRIDE THE SCORE, ALWAYS. Tradeability is a fact about the order
   book. No quantity of good signal makes an untradeable name tradeable, and a
   100-scoring name below the turnover floor must still come back NO ACTION.

5. LESS EVIDENCE MEANS A SCORE CLOSER TO NEUTRAL. Disagreeing families, a
   missing family and missing components each shrink the result. A 78 from two
   agreeing families and a 78 from one family with three gaps are different
   claims and must not print the same.

6. THE NULL RESULT SHIPS WITH THE SCORE. `provenance()` carries the measured
   finding that the price composite has no detectable edge, and it degrades to
   a LOUDER warning when the artifact is missing, never to silence.

The wording is free to change. Those six are not.
"""

from __future__ import annotations

import pytest

from _lib import verdict as V


# --------------------------------------------------------------------------- #
# Payload builders — the confluence leg shapes the readers consume
# --------------------------------------------------------------------------- #
def leg(data, ok=True, error="boom"):
    return {"ok": ok, "data": data} if ok else {"ok": False, "error": error}


def anomaly(bias="Accumulation", recent=3, days=10, regime="accumulation"):
    return leg({
        "stats": {"recentCount": recent, "recentDays": days,
                  "recentFlowBias": bias, "anomalyCount": 12},
        "accumulation": {"current": {"direction": regime} if regime else None},
    })


def technical(passed=7, scored=8, verdict_word="CONSTRUCTIVE", has_long=True):
    return leg({
        "hasLongTerm": has_long,
        "longTerm": {"view": {"verdict": verdict_word, "tone": "bull",
                              "passed": passed, "scored": scored}},
        "summary": {"trend": "Bullish", "trend_tone": "bull"},
    })


def valuation(prob=0.80, terminal=0.35, verdict_word="UNDERVALUED"):
    return leg({
        "engine": "DCF", "price": 1000.0, "priceLabel": "Rp 1,000",
        "verdict": verdict_word,
        "monteCarlo": {"probUndervalued": prob, "p50": 1400.0, "p50Label": "Rp 1,400"},
        "baseCase": {"terminalShare": terminal},
    })


def quality(applicable=True, score=8, altman="safe", beneish="clean",
            cause="financial"):
    if not applicable:
        reasons = {
            "financial": "Piotroski, Altman and Beneish were all built on "
                         "non-financial firms.",
            "no-statements": "No financial statements came back for this listing.",
            "unknown-sector": "No sector or industry came back for this listing, so "
                              "there is no way to tell whether the models apply.",
        }
        return leg({"applicable": False, "cause": cause,
                    "reason": reasons.get(cause, "unavailable")})
    return leg({
        "applicable": True,
        "piotroski": {"score": score, "maxScore": 9, "band": "strong"},
        "altman": {"score": 6.2, "band": altman},
        "beneish": {"score": -2.6, "band": beneish},
    })


def tape_payload(direction="accumulation", score=80.0, top_five=0.10,
                 band="ordinary", calibrated=True, available=True):
    """A `tape.read` payload. Built by hand rather than by running the module so
    the verdict's handling of each state is testable without market data."""
    if not available:
        return {"available": False, "reason": "not enough sessions"}
    return {
        "available": True, "direction": direction, "score": score,
        "calibrated": calibrated, "significant": direction != "unreadable",
        "lift": 0.30, "excessLift": 0.23, "tStat": 3.1, "pValue": 0.002,
        "reading": "On its heaviest sessions it closed nearer the high.",
        "concentration": {"available": True, "topFiveShare": top_five,
                          "effectiveDays": 120.0, "band": band, "severe": 0.36,
                          "caution": 0.21, "calibrated": True, "sessions": 252},
    }


# The DEFAULT register is deliberately constructive — a wide float and a small
# buyback — so that `scored()` produces the all-three-families-agree case. A
# fixture whose default lands in the neutral band would make the strongest
# branch of `_agreement` unreachable from most tests, which is how the branch
# that matters most ends up untested.
def pattern_payload(usable=True, score=42.0, calibrated=True, available=True,
                    detections=1):
    """A `patterns.read` payload. `usable` is the field that decides whether the
    component reads at all — it is true only where a detected formation's
    forward return survived correction."""
    if not available:
        return {"available": False, "reason": "not enough history"}
    return {
        "available": True, "calibrated": calibrated, "usable": usable,
        "score": score if usable else None,
        "detections": [{"pattern": "headAndShoulders", "label": "Head and shoulders",
                        "bias": "down", "significant": usable,
                        "firingRate": 0.22, "observations": 1475,
                        "forward": {"horizonDays": 63, "meanExcess": -0.032}}
                       for _ in range(detections)],
        "survivors": ["headAndShoulders"] if usable else [],
        "reading": "one formation", "refused": [],
    }


def structure_payload(band="fine", reward_risk=2.4, available=True):
    if not available:
        return {"available": False, "reason": "no usable support or resistance"}
    return {"available": True, "band": band, "price": 1000.0, "atr": 25.0,
            "support": 960.0, "resistance": 1096.0,
            "riskToSupport": 0.04, "rewardToResistance": 0.04 * reward_risk,
            "rewardRisk": reward_risk, "unboundedUpside": False,
            "noSupport": False, "atSupport": False, "atResistance": False,
            "reading": "structure reading"}


def register_payload(free=0.55, annualised=-0.06, observations=20, band="retiring",
                     available=True, float_ok=True, issuance_ok=True):
    """An `ownership.read` payload."""
    if not available:
        return {"available": False, "reason": "no register data"}
    floats = ({"available": True, "freeFloat": free, "insidersHeld": 1 - free,
               "band": ("critical" if free < 0.08 else "tight" if free < 0.20
                        else "moderate" if free < 0.40 else "comfortable"),
               "score": 50.0 + (free - 0.30) * 100.0,
               "reading": f"{free * 100:.0f}% outside insider hands.",
               "institutionsHeld": 0.1, "institutionsCount": 40}
              if float_ok else {"available": False, "reason": "no float figure"})
    issued = ({"available": True, "annualised": annualised, "years": 3.0,
               "observations": observations, "band": band, "largestStep": 0.02,
               "largestStepAt": None, "score": 50.0 - annualised * 128.0,
               "reading": f"Share count {annualised * 100:+.0f}% a year."}
              if issuance_ok else {"available": False, "reason": "no share history"})
    return {"available": True, "float": floats, "issuance": issued,
            "floatTurnover": 0.004, "floatShares": 1e9,
            "reading": "register reading",
            "institutions": {"percentHeld": 0.1, "count": 40, "note": "context"}}


def legs(**overrides):
    base = {"anomaly": anomaly(), "technical": technical(),
            "valuation": valuation(), "quality": quality()}
    base.update(overrides)
    return base


def rank_row(composite=80.0, coverage=1.0, rank=1):
    return {"ticker": "T.JK", "composite": composite, "coverage": coverage,
            "rank": rank, "signalsAvailable": 7, "signalsTotal": 7,
            "signals": {"lowVolatility": {"raw": 0.30}}}


def liquid(turnover=5.0e10):
    return {"medianDollarVolume": turnover}


def scored(**kwargs):
    """A fully specified, tradeable, everything-available call."""
    payload = {"legs": legs(), "rank_row": rank_row(), "liquidity": liquid(),
               "market": "ID", "latest_close": 1000.0, "annual_volatility": 0.30,
               "tape_result": tape_payload(), "register_result": register_payload(),
               "pattern_result": pattern_payload(),
               "structure_result": structure_payload()}
    payload.update(kwargs)
    return V.score("T.JK", **payload)


# ============================================================================ #
# 1. The published surfaces must not be able to reach this module
# ============================================================================ #
def test_the_published_synthesis_does_not_import_the_composite():
    """`PRODUCT.md` constraint 1 holds because of exactly this.

    `explain.for_synthesis` and `pretrade.assess` are the two payloads the
    single-company view renders, and both are guarded against aggregates by
    their own suites. Those guards are worth nothing if either module starts
    reading a score from here, so the import direction is asserted directly.
    """
    import ast
    import inspect

    from _lib import explain, pretrade

    # AST, not a substring search: both modules use the word "verdict" in prose
    # constantly — it is the app's own term for a lens's reading — so a text
    # match would fail on a docstring. What must not exist is an IMPORT.
    for module in (explain, pretrade):
        tree = ast.parse(inspect.getsource(module))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[-1] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.update(alias.name for alias in node.names)
                if node.module:
                    imported.add(node.module.split(".")[-1])
        assert "verdict" not in imported, (
            f"{module.__name__} imports `verdict`. The private scanner's composite "
            f"must never reach a published surface - see PRODUCT.md constraint 1.")


def test_the_verdict_carries_its_own_refusal_of_advice():
    result = scored()
    assert "not investment advice" in result["caveat"].lower()
    assert "not a forecast" in result["caveat"].lower()


# ============================================================================ #
# 2. Nothing is imputed
# ============================================================================ #
def test_a_missing_lens_removes_its_weight_rather_than_scoring_fifty():
    """The failure this prevents is invisible in the output.

    Imputing 50 for a lens that did not return produces a score, a coverage of
    100% and no complaint. The name is then dragged toward the middle of the
    pack for the crime of having a filing gap, and the report calls that a
    measurement — the exact failure `ranking.py` names about median imputation.
    """
    with_flow = scored()
    without_flow = scored(legs=legs(anomaly=leg(None, ok=False)))

    flow = next(c for c in without_flow["components"] if c["key"] == "flow")
    assert flow["available"] is False
    assert flow["score"] is None
    assert flow["effectiveWeight"] == 0.0
    assert without_flow["coverage"] < with_flow["coverage"]
    assert without_flow["componentsRead"] == with_flow["componentsRead"] - 1


def test_coverage_is_the_share_of_intended_weight_that_actually_read():
    result = scored(legs=legs(quality=leg(None, ok=False)))
    intended = sum(c["weight"] for c in V.COMPONENTS)
    # `coverage` is rounded to three places on the wire, so the tolerance is the
    # rounding and not a fudge factor.
    assert result["coverage"] == pytest.approx(
        (intended - V.COMPONENT_BY_KEY["quality"]["weight"]) / intended, abs=5e-4)


def test_a_family_with_no_readable_component_is_absent_not_neutral():
    result = scored(legs=legs(valuation=leg(None, ok=False),
                              quality=leg(None, ok=False)))
    assert result["families"]["filings"] is None
    # Still cross-checked: the register is a third body of data and survived.
    # An absent family is absent, never a neutral 50 averaged in.
    assert result["families"]["price"] is not None
    assert result["families"]["register"] is not None
    assert result["agreement"]["state"] != "single"


def test_only_one_surviving_family_is_reported_as_no_cross_check():
    result = scored(legs=legs(valuation=leg(None, ok=False),
                              quality=leg(None, ok=False)),
                    register_result=register_payload(available=False))
    assert result["agreement"]["state"] == "single"
    assert result["crossChecked"] is False
    assert "one body of data" in result["agreement"]["text"]


# ============================================================================ #
# 3. A refusal is not a gap
# ============================================================================ #
def test_quality_on_a_bank_is_refused_and_never_a_low_score():
    """IDX is heavily weighted toward banks. Scoring a refusal as a zero — or as
    a neutral 50 — would systematically misprice the largest names in the market
    for a screen that was never applicable to them."""
    result = scored(legs=legs(quality=quality(applicable=False)))
    component = next(c for c in result["components"] if c["key"] == "quality")

    assert component["available"] is False
    assert component["refused"] is True
    assert component["score"] is None
    assert "non-financial firms" in component["reason"]
    assert any("Refused" in reason for reason in result["reasons"])


def test_a_coverage_gap_is_not_dressed_up_as_the_bank_refusal():
    """The wrong answer this prevents was found on the first real IDX scan.

    Seven small caps - a tape manufacturer, a hotel operator, a chocolate maker -
    came back `applicable: false` because Yahoo returned no statements for them,
    and the report said "the models do not transfer to a bank or insurer". That
    is a plausible sentence about the wrong company. `quality.analyze` carries
    `cause` so the two never have to be told apart by reading the prose.
    """
    gap = scored(legs=legs(quality=quality(applicable=False, cause="no-statements")))
    component = next(c for c in gap["components"] if c["key"] == "quality")
    assert component["available"] is False
    assert component["refused"] is False
    assert "bank or insurer" not in (component["reason"] or "")
    assert "statements" in component["reason"]


def test_an_unknown_sector_is_a_gap_and_never_the_bank_refusal():
    """`quality.analyze` declines to guess when the sector lookup came back
    empty, because on a throttled fetch a bank otherwise gets an F-score. That
    refusal-to-guess is a coverage problem and must not read as the designed
    one, which says something true about the models."""
    unknown = scored(legs=legs(quality=quality(applicable=False,
                                               cause="unknown-sector")))
    component = next(c for c in unknown["components"] if c["key"] == "quality")
    assert component["available"] is False
    assert component["refused"] is False


def test_a_failed_lens_is_reported_as_not_read_rather_than_refused():
    result = scored(legs=legs(quality=leg(None, ok=False)))
    component = next(c for c in result["components"] if c["key"] == "quality")
    assert component["available"] is False
    assert component["refused"] is False


def test_distress_caps_the_quality_component_instead_of_subtracting_from_it():
    """Solvency is not a gradient a good trading record can offset.

    Eight of nine health checks passing inside the distress zone is still inside
    the distress zone. A subtraction would let the F-score buy its way out.
    """
    healthy = V.read_quality(legs(quality=quality(score=9, altman="safe")))
    distressed = V.read_quality(legs(quality=quality(score=9, altman="distress")))
    assert healthy["score"] == pytest.approx(100.0)
    assert distressed["score"] <= 25.0


# ============================================================================ #
# 4. Gates override the score
# ============================================================================ #


def test_a_stop_too_far_below_gates_as_hard_as_a_lopsided_ratio():
    """THE WORST ENTRY STATE MUST NOT BE THE ONE THAT ESCAPES THE GATE.

    `structure._band` returns the first state that matches and tests the risk
    DISTANCE before the ratio, so `riskTooWide` and `bad` are mutually exclusive
    labels rather than points on a scale. The gate originally read `== "bad"`,
    which meant a name whose only defended floor was 35% below took the more
    severe diagnosis and sailed through, while a name with a merely lopsided
    ratio was stopped.

    Found on the highest-scoring name in a full IDX sweep: SRSN read STRONG_BUY
    at 74.6 with its nearest support 35.2% underneath and no gate at all.
    """
    wide = scored(structure_result={
        **structure_payload(band="riskTooWide", reward_risk=0.73),
        "riskToSupport": 0.352, "rewardToResistance": 0.258})
    gate = next((g for g in wide["gates"] if g["id"] == "poorEntry"), None)
    assert gate is not None, "a stop 35% away did not gate"
    assert gate["action"] == "HOLD"
    assert wide["action"] not in ("BUY", "STRONG_BUY")
    # The wording has to name the actual problem, which is not a bad ratio.
    assert "too far to be a stop" in gate["detail"]
    assert "35.2%" in gate["detail"]


def test_a_lopsided_ratio_still_gates_and_still_says_why():
    bad = scored(structure_result=structure_payload(band="bad", reward_risk=0.2))
    gate = next((g for g in bad["gates"] if g["id"] == "poorEntry"), None)
    assert gate is not None
    assert "overhead" in gate["detail"] and "0.20 to 1 against" in gate["detail"]


def test_a_sound_entry_does_not_gate():
    for band in ("fine", "poor", "unbounded"):
        result = scored(structure_result=structure_payload(band=band))
        assert not any(g["id"] == "poorEntry" for g in result["gates"]), band


def test_a_stop_inside_the_noise_withholds_the_ratio_without_gating():
    """WITHHOLDING A NUMBER IS NOT THE SAME AS CONDEMNING THE TRADE.

    Buying a level the market has defended is a real setup; what is refused is
    the reward-to-risk figure computed from a floor half a day's range below,
    which grows as the stop gets more fragile. Gating it would throw away the
    setup along with the arithmetic.
    """
    result = scored(structure_result={
        **structure_payload(band="riskInsideNoise"),
        "rewardRisk": None, "rewardRiskRaw": 15.0, "ratioWithheld": True,
        "atSupport": True})
    assert not any(g["id"] == "poorEntry" for g in result["gates"])
    assert result["action"] in ("BUY", "STRONG_BUY", "HOLD")


def test_an_illiquid_name_is_no_action_however_well_it_scores():
    result = scored(rank_row=rank_row(composite=99.0),
                    liquidity=liquid(turnover=1.0e6))
    assert result["action"] == "NO_ACTION"
    assert any(gate["id"] == "illiquid" for gate in result["gates"])
    # The score itself is NOT suppressed. A reader who overrides the gate has to
    # be able to see what they are overriding.
    assert result["score"] is not None and result["score"] > 60


def test_unmeasured_turnover_gates_exactly_as_hard_as_measured_illiquidity():
    """Unmeasured is not clear. The two states have different explanations and
    the same consequence, which is the point."""
    result = scored(liquidity=None)
    assert result["action"] == "NO_ACTION"
    assert any(gate["id"] == "turnoverUnknown" for gate in result["gates"])


def test_a_name_resting_on_the_tick_floor_is_gated():
    result = scored(latest_close=50.0)
    assert result["action"] == "NO_ACTION"
    assert any(gate["id"] == "tickFloor" for gate in result["gates"])


def test_one_lens_is_not_a_composite():
    result = scored(legs={"anomaly": anomaly()}, rank_row=None,
                    tape_result=None, register_result=None, pattern_result=None)
    assert result["action"] == "NO_ACTION"
    assert any(gate["id"] == "insufficientEvidence" for gate in result["gates"])


def test_distress_alone_caps_at_hold_and_with_flagged_accruals_at_avoid():
    capped = scored(legs=legs(quality=quality(altman="distress")))
    assert capped["action"] == "HOLD"

    both = scored(legs=legs(quality=quality(altman="distress", beneish="flagged")))
    assert both["action"] == "AVOID"


@pytest.mark.parametrize("gate_action", ["NO_ACTION", "AVOID", "HOLD"])
def test_a_gate_never_raises_an_action(gate_action):
    """A gate is a ceiling. One that could promote a name would be a
    recommendation dressed as a safety check."""
    order = V.ACTION_ORDER
    for action in order:
        capped = V._cap_action(action, gate_action if gate_action != "NO_ACTION"
                               else "AVOID")
        assert order.index(capped) <= order.index(action)


# ============================================================================ #
# 5. Less evidence means a score closer to neutral
# ============================================================================ #
def test_disagreeing_families_are_pulled_harder_toward_neutral_than_agreeing_ones():
    agreeing = scored()
    disagreeing = scored(legs=legs(valuation=valuation(prob=0.05,
                                                       verdict_word="OVERVALUED"),
                                    quality=quality(score=1)))
    assert agreeing["agreement"]["state"] == "agree"
    assert disagreeing["agreement"]["state"] == "disagree"
    assert disagreeing["conviction"] == "low"
    assert disagreeing["shrink"]["agreement"] < agreeing["shrink"]["agreement"]
    assert abs(disagreeing["shrunkScore"] - 50) < abs(agreeing["shrunkScore"] - 50)


def test_a_single_family_cannot_reach_high_conviction():
    result = scored(legs=legs(valuation=leg(None, ok=False),
                              quality=leg(None, ok=False)),
                    register_result=register_payload(available=False))
    assert result["conviction"] == "low"
    assert result["action"] != "STRONG_BUY"


def test_one_family_dissenting_is_a_disagreement_and_not_an_outvoted_minority():
    """Three families do not vote. The whole argument for combining independent
    sources is that a dissent from one of them is information; treating it as a
    minority to be outvoted throws away the only thing the third source added."""
    result = scored(register_result=register_payload(free=0.45, annualised=0.30,
                                                     band="severe"))
    assert result["families"]["register"]["side"] == -1
    assert result["agreement"]["state"] == "disagree"
    assert result["conviction"] == "low"


def test_strong_buy_requires_high_conviction_as_well_as_the_score():
    """A 74 assembled from one family with two gaps is not a strong anything,
    and shrinkage alone does not always drag it under the band."""
    result = scored()
    if result["score"] >= V.BANDS[0][0]:
        assert result["conviction"] == "high"
    for conviction in ("low", "medium"):
        assert conviction != V.STRONG_BUY_REQUIRES


def test_shrinkage_never_flips_the_side_of_the_score():
    """Pulling toward 50 is not the same as changing the answer. A raw 70 must
    never shrink to below 50, whatever the deficiency."""
    for kwargs in ({}, {"legs": legs(quality=leg(None, ok=False))},
                   {"legs": legs(valuation=leg(None, ok=False),
                                 quality=leg(None, ok=False))}):
        result = scored(**kwargs)
        raw, shrunk = result["rawScore"], result["shrunkScore"]
        assert (raw - 50) * (shrunk - 50) >= 0
        assert abs(shrunk - 50) <= abs(raw - 50) + 1e-9


def test_each_body_of_data_gets_one_vote_not_one_vote_per_component():
    """Four price components, two filings ones and two register ones are still
    three bodies of data. Letting the count decide would give the price record
    most of the say purely because price signals are cheaper to compute."""
    result = scored()
    families = [f for f in result["families"].values() if f is not None]
    assert len(families) == 3
    assert all(f["vote"] == 1.0 for f in families), (
        "every family read in full here, so every family should hold a whole vote")
    expected = sum(f["score"] for f in families) / len(families)
    assert result["rawScore"] == pytest.approx(expected, abs=0.06)


def test_a_half_read_family_casts_less_than_a_whole_vote():
    """A family reporting on half the evidence it was supposed to bring is
    making half a claim. This is COVERAGE, not the component count: the floor
    stops a thin family vanishing, and a one-component family that read fully
    still votes in full."""
    full = scored()
    thin = scored(register_result=register_payload(issuance_ok=True, float_ok=False))

    assert full["families"]["register"]["vote"] == 1.0
    assert thin["families"]["register"]["vote"] < 1.0
    assert thin["families"]["register"]["vote"] >= V.MIN_FAMILY_VOTE


# ============================================================================ #
# 6. The null result ships with the score
# ============================================================================ #
def test_provenance_carries_the_measured_null_result():
    provenance = V.provenance()
    assert provenance["available"] is True
    assert provenance["significant"] == 0
    assert provenance["headline"]
    assert "price-and-volume composite" in provenance["appliesTo"]


def test_a_missing_backtest_artifact_gets_louder_not_quieter(monkeypatch):
    from _lib import ranking

    monkeypatch.setattr(ranking, "validation", lambda universe_id=None:
                        {"available": False})
    provenance = V.provenance()
    assert provenance["available"] is False
    assert "NOT been measured" in provenance["headline"]


# ============================================================================ #
# Penalties — calibrated, or they do not count
# ============================================================================ #
def flag(check_id="x", rate=0.05, band="bad", classification="flag"):
    return {"id": check_id, "classification": classification, "firingRate": rate,
            "universeLabel": "the IDX30", "where": "Quality",
            "explain": {"label": f"Check {check_id}", "band": band,
                        "reading": "fired"}}


def test_a_rare_flag_costs_more_than_a_common_one():
    rare = V._penalties({"flags": [flag(rate=0.02)]})
    common = V._penalties({"flags": [flag(rate=0.30)]})
    assert rare[0]["points"] > common[0]["points"]


def test_a_base_condition_costs_nothing():
    """`pretrade.py`'s own argument: a condition firing on a third of a universe
    describes the equity market, and charging a company for it manufactures a
    finding out of a base rate."""
    assert V._penalties({"baseConditions": [flag(rate=0.40)]}) == []
    assert V._penalties({"flags": [flag(rate=0.40, classification="base")]}) == []


def test_an_uncalibrated_condition_can_never_cost_points():
    unmeasured = {"id": "y", "classification": "flag", "explain": {"label": "Y"}}
    assert V._penalties({"flags": [unmeasured]}) == []


def test_the_penalty_total_is_capped_because_flags_are_correlated():
    many = {"flags": [flag(check_id=str(i), rate=0.01) for i in range(10)]}
    result = scored(pretrade_result=many)
    assert result["penaltyTotal"] == V.MAX_TOTAL_PENALTY
    assert result["penaltyCapped"] is True


# ============================================================================ #
# Degradation — the empty case must be a sentence, not an exception
# ============================================================================ #
def test_nothing_at_all_returns_a_stated_no_action():
    result = V.score("EMPTY.JK")
    assert result["action"] == "NO_ACTION"
    assert result["score"] is None
    assert result["conviction"] == "none"
    assert result["reasons"]
    assert result["sizing"]["applicable"] is False


def test_every_component_reader_survives_a_junk_payload():
    """A reader that raises takes down a whole scan row. Each one is handed the
    shapes a failed upstream actually produces."""
    for payload in ({}, {"anomaly": {"ok": True, "data": None}},
                    {"technical": leg({"longTerm": {}})},
                    {"valuation": leg({"monteCarlo": {}})},
                    {"quality": leg({"applicable": True, "piotroski": {}})}):
        for reader in (V.read_trend, V.read_flow, V.read_value, V.read_quality):
            outcome = reader(payload)
            assert "available" in outcome
    assert V.read_price_rank({"composite": None})["available"] is False
    assert V.read_price_rank(None)["available"] is False


# ============================================================================ #
# Sizing is arithmetic and says so
# ============================================================================ #
def test_a_calmer_name_is_sized_larger_at_the_same_risk_budget():
    calm = scored(annual_volatility=0.15)
    wild = scored(annual_volatility=0.60)
    assert calm["sizing"]["weight"] > wild["sizing"]["weight"]
    assert calm["sizing"]["weight"] <= 0.10


def test_sizing_is_not_computed_for_anything_outside_the_buy_bands():
    result = scored(rank_row=rank_row(composite=2.0),
                    legs=legs(valuation=valuation(prob=0.01,
                                                   verdict_word="OVERVALUED"),
                              quality=quality(score=0),
                              technical=technical(passed=0, scored=8),
                              anomaly=anomaly(bias="Distribution",
                                              regime="distribution")))
    assert result["action"] in {"AVOID", "REDUCE"}
    assert result["sizing"]["applicable"] is False


# ============================================================================ #
# The tape component — the bandarmology proxy, and what it refuses to claim
# ============================================================================ #
def test_an_unreadable_tape_is_a_reading_and_not_a_gap():
    """"Unreadable" means the test ran and the answer was ordinary. That is a
    measurement. Treating it as unavailable would remove its weight from the
    blend and quietly reward every name the test found nothing in."""
    result = scored(tape_result=tape_payload(direction="unreadable", score=48.0))
    component = next(c for c in result["components"] if c["key"] == "tape")
    assert component["available"] is True
    assert component["score"] == 48.0


def test_an_uncalibrated_market_contributes_no_tape_component_at_all():
    """A direction computed against the wrong null is worse than no direction.
    The median listing has a positive heavy-day lift, so testing against zero
    calls the median stock an accumulation candidate — the bug the calibration
    artifact exists to remove. Without a baseline, the component is absent."""
    result = scored(tape_result=tape_payload(calibrated=False))
    component = next(c for c in result["components"] if c["key"] == "tape")
    assert component["available"] is False
    assert component["effectiveWeight"] == 0.0
    assert "baseline" in component["reason"]


def test_the_tape_lives_in_the_price_family_because_it_reads_price_and_volume():
    """It must not become a fourth body of data. It reads the same two series
    `whale.py` and `accumulation.py` read, and filing it separately would let
    one dataset cast two votes — the exact double-count the family split
    exists to prevent."""
    assert V.COMPONENT_BY_KEY["tape"]["family"] == "price"
    assert V.COMPONENT_BY_KEY["tape"]["evidence"] == "weak"


def test_volume_concentration_gates_but_never_scores():
    """It is not directional. A stock whose year happened in five sessions is
    not thereby good or bad, it is unsizeable — which is a gate, not points."""
    ordinary = scored(tape_result=tape_payload(top_five=0.10, band="ordinary"))
    episodic = scored(tape_result=tape_payload(top_five=0.55, band="severe"))

    assert ordinary["score"] == episodic["score"], (
        "concentration moved the score; it is not a directional quantity")
    assert any(g["id"] == "episodicVolume" for g in episodic["gates"])
    assert episodic["action"] in {"HOLD", "REDUCE", "AVOID"}


# ============================================================================ #
# The register — the third body of data
# ============================================================================ #
def test_the_register_is_its_own_family_and_not_a_fifth_lens():
    for key in ("float", "issuance"):
        assert V.COMPONENT_BY_KEY[key]["family"] == "register"
    assert set(V.FAMILIES) == {"price", "filings", "register"}


def test_dilution_scores_worse_than_a_buyback():
    diluting = scored(register_result=register_payload(annualised=0.20, band="material"))
    retiring = scored(register_result=register_payload(annualised=-0.20, band="retiring"))
    assert diluting["score"] < retiring["score"]


def test_heavy_issuance_gates_at_hold_however_good_the_rest_is():
    result = scored(rank_row=rank_row(composite=99.0),
                    register_result=register_payload(annualised=0.40, band="severe"))
    assert any(g["id"] == "heavyIssuance" for g in result["gates"])
    assert result["action"] not in {"BUY", "STRONG_BUY"}


def test_a_micro_float_gates_at_hold_rather_than_being_refused():
    """It describes the instrument, not the business. Refusing outright would
    say something about the company that the float does not support."""
    result = scored(rank_row=rank_row(composite=99.0),
                    register_result=register_payload(free=0.05))
    gate = next(g for g in result["gates"] if g["id"] == "microFloat")
    assert gate["action"] == "HOLD"
    assert result["action"] not in {"BUY", "STRONG_BUY"}
    assert result["score"] is not None, "the score stays visible under a gate"


def test_half_a_register_still_reads_rather_than_being_discarded():
    """One half is enough for a reading; the missing half becomes coverage,
    never an imputed 50."""
    result = scored(register_result=register_payload(issuance_ok=False))
    float_component = next(c for c in result["components"] if c["key"] == "float")
    issuance_component = next(c for c in result["components"] if c["key"] == "issuance")
    assert float_component["available"] is True
    assert issuance_component["available"] is False
    assert result["families"]["register"] is not None


def test_a_thinly_reported_share_count_bends_its_weight_not_its_score():
    """A three-year trend read from four filing dates is a weaker version of the
    same statement, not a different statement. Renormalising the score instead
    would move a thinly reported name toward the middle and call it a finding."""
    thin = scored(register_result=register_payload(observations=4))
    thick = scored(register_result=register_payload(observations=30))
    thin_component = next(c for c in thin["components"] if c["key"] == "issuance")
    thick_component = next(c for c in thick["components"] if c["key"] == "issuance")

    assert thin_component["score"] == thick_component["score"]
    assert thin_component["effectiveWeight"] < thick_component["effectiveWeight"]


def test_institutional_ownership_is_never_a_component():
    """"Somebody professional owns this" is an argument from authority, and the
    holders are mostly index funds with no view. It renders as context."""
    assert "institutions" not in V.COMPONENT_BY_KEY
    assert not any("institution" in c["key"].lower() for c in V.COMPONENTS)


def test_a_silent_family_neither_supports_nor_blocks_high_conviction():
    """The bar is TWO INDEPENDENT SOURCES ACTIVELY AGREEING, not unanimity.

    The share register reads neutral for the median listing by construction — an
    ordinary float and a flat share count is what most companies have. Requiring
    all three families to take a direction made high conviction unreachable: on a
    real IDX30 sweep it fell to zero of twenty-nine names, and nothing in the
    output said why. A source with nothing to say abstains; it does not dissent.
    """
    silent = scored(register_result=register_payload(free=0.30, annualised=0.0,
                                                     band="flat"))
    assert silent["families"]["register"]["side"] == 0
    assert silent["agreement"]["state"] == "agree"
    assert silent["conviction"] == "high"
    assert "unremarkable" in silent["agreement"]["text"]


def test_one_lone_directional_family_is_still_only_medium_conviction():
    """Two agreeing sources is the bar. One source and two abstentions is not a
    cross-check, whatever the score."""
    result = scored(
        legs=legs(valuation=valuation(prob=0.50, verdict_word="FAIRLY VALUED"),
                  quality=quality(score=5, altman="grey")),
        register_result=register_payload(free=0.30, annualised=0.0, band="flat"))
    if result["agreement"]["state"] == "oneNeutral":
        assert result["conviction"] == "medium"
        assert result["action"] != "STRONG_BUY"
