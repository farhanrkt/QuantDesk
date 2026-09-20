"""
neglect.py
==========
Solid businesses the composite is structurally unable to recommend.

THE PROBLEM, MEASURED BEFORE IT WAS BUILT
------------------------------------------
`verdict.score` blends three families and shrinks the result toward 50 when they
disagree. That rule is right in general — two bodies of evidence pointing
opposite ways IS less information than two agreeing — but it treats two
completely different disagreements as the same thing:

    the filings like it and the price does not   -> a cheap good business
    the price likes it and the filings do not    -> an expensive bad business

Both get pulled to the middle. On a full sweep of 775 Indonesian listings, 82
names had strong filings and a weak price family, and NOT ONE of them was a buy:
29 read HOLD and 53 were gated. Mean score 51.2, which is to say "no opinion".
The 51 names where both families agreed produced ten buys.

So the scanner can only recommend a company whose price has already confirmed
what the filings say. That is not a tuning problem. Five of the seven signals in
`ranking.py` — momentum, trend, nearHigh, shallowDrawdown, relativeStrength —
reward a stock for having already gone up, so a solid business that has fallen
scores badly on the price family BY CONSTRUCTION, and falling is exactly what
makes it cheap.

WHAT THIS MODULE IS, AND WHAT IT IS NOT
----------------------------------------
It is a SCREEN, not a tenth component. It does not touch the score, and adding
it to the blend would be self-defeating: the blend's own shrink is the mechanism
that hides these names.

It selects on three conditions that must hold together, because any one alone is
a well-known way to lose money:

  CHEAP, by the valuation lens already computed. Not a second opinion on price —
  the same DCF/DDM the value component reads.
  SOLID, by the quality lens already computed: Piotroski, Altman, Beneish. Cheap
  without this is a value trap, and the screen's whole premise is that the
  business is fine and the price is not.
  UNATTENDED, by the share register: institutional ownership and analyst
  coverage near zero. This is the part that distinguishes "underrated" from
  merely "down". A company fifty analysts cover and everyone hates is priced;
  one nobody has looked at may simply not have been read yet.

NO MOMENTUM FILTER, DELIBERATELY. It would be easy to add "and the price has
stopped falling" to avoid catching a falling knife, and that is precisely the
bias this module exists to escape — it would reintroduce the constraint that
made the composite blind. The drawdown is REPORTED as context so a reader can
apply their own judgement, and it is not a criterion.

THIS SCREEN CANNOT BE BACKTESTED, AND SAYING SO IS THE POINT
--------------------------------------------------------------
`PRODUCT.md` constraint 2 requires that anything implying a return prediction be
measured offline first. That measurement is NOT AVAILABLE here, and the reason is
the same wall `scripts/backtest_verdict.py` already hit and published: this data
source has no point-in-time filings. Reconstructing "was this company cheap and
solid in March 2026" means reading the statements as they stood then, and what
comes back is the statements as they stand today — restated, revised, and
including quarters nobody had seen.

The attention half is worse. Institutional ownership and analyst coverage arrive
as a CURRENT SNAPSHOT with no history at all, so there is no version of
"unattended in March" to test on. A backtest of this screen would not be
optimistic, it would be fictional.

So there is no `calibrate_neglect.py`, deliberately, and the honest route is the
slow one: `scanlog.py` records what the screen selected on the day it selected
it, and in some months there will be enough resolved calls to say something. The
same instrument, and the same wait, that the blended score already depends on for
the half of itself that cannot be reconstructed.

UNTIL THEN THIS MAKES NO PREDICTIVE CLAIM. It is a list of names the composite
has no opinion about, and a statement of why it has none. That is worth having —
a blind spot you can see is a different thing from one you cannot — and it is
not a recommendation.
"""

from __future__ import annotations

from typing import Optional

# How cheap the valuation lens must read. 60 on a 0-100 scale where 50 is
# "fairly priced": the model has to actively say cheap, not merely fail to say
# expensive. Below this the screen would fill with names nobody has valued.
CHEAP_AT = 60.0

# How healthy the accounting screens must read. Also 60, and this is the
# condition that separates the screen from a list of things that have fallen.
# Piotroski, Altman and Beneish all feed it; a distress reading cannot clear it.
SOLID_AT = 60.0

# Institutional ownership at or below which a listing counts as unattended.
# Five percent is low enough that no fund has taken a position worth reporting.
# It is a threshold on ATTENTION, not on quality or size.
UNATTENDED_HELD = 0.05

# And the analyst count. Two or fewer is not coverage; it is one broker's
# obligation to a client.
UNATTENDED_ANALYSTS = 2

# Below this free float the screen declines rather than selecting. A company
# with almost no tradeable stock is not underrated, it is unavailable — and
# `verdict` already gates it. Included here so the screen does not spend its
# list on names the reader could not buy.
MIN_FREE_FLOAT = 0.10


def _finite(value) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _component(verdict_row: dict, key: str) -> Optional[float]:
    for component in verdict_row.get("components") or []:
        if component.get("key") == key and component.get("available"):
            return _finite(component.get("score"))
    return None


def attention(register_result: Optional[dict]) -> dict:
    """How much of the market is actually looking at this company.

    THE TWO FIGURES ARE NOT INTERCHANGEABLE and both are reported. Institutional
    ownership says whether anyone has bought it; analyst count says whether
    anyone has written about it. A name can have neither, which is the case this
    screen is built for, or it can have holders and no coverage — common for a
    listing an index fund owns mechanically and nobody researches.
    """
    register = register_result if isinstance(register_result, dict) else {}

    # TWO PAYLOAD SHAPES REACH THIS, AND READING ONLY ONE SELECTED NOTHING.
    # `market_data.share_register` returns the raw Yahoo fields flat; the
    # scanner stores `ownership.read`'s assembled output, which nests the same
    # figures under `institutions`. Reading only the flat shape found no
    # institutional holding on ANY name in a 775-name sweep — so every name
    # looked unattended, the free-float guard was the only thing left standing,
    # and the screen selected zero. A silent nothing, from a key that was simply
    # somewhere else.
    nested = register.get("institutions") if isinstance(
        register.get("institutions"), dict) else {}
    held = _finite(register.get("institutionsPercentHeld"))
    if held is None:
        held = _finite(nested.get("percentHeld"))
    count = _finite(register.get("institutionsCount"))
    if count is None:
        count = _finite(nested.get("count"))
    recommendations = register.get("recommendations") or nested.get("recommendations")
    analysts = None
    if isinstance(recommendations, dict):
        analysts = _finite(recommendations.get("numberOfAnalystOpinions"))
    elif isinstance(recommendations, list):
        analysts = float(len(recommendations))

    known = held is not None or count is not None or analysts is not None
    unattended = bool(
        known
        and (held is None or held <= UNATTENDED_HELD)
        and (analysts is None or analysts <= UNATTENDED_ANALYSTS))

    return {
        "known": known,
        "institutionsHeld": held,
        "institutionsCount": int(count) if count is not None else None,
        "analysts": int(analysts) if analysts is not None else None,
        "unattended": unattended,
        "reading": _attention_reading(known, held, count, analysts, unattended),
    }


def _attention_reading(known: bool, held: Optional[float], count: Optional[float],
                       analysts: Optional[int], unattended: bool) -> str:
    if not known:
        return ("Nothing came back about who holds this or who covers it, so how "
                "closely it is watched is unmeasured rather than low.")
    parts = []
    if held is not None:
        parts.append(f"institutions hold {held * 100:.1f}%"
                     + (f" across {int(count)} holders" if count else ""))
    if analysts is not None:
        parts.append(f"{int(analysts)} analyst{'' if analysts == 1 else 's'} cover it")
    body = " and ".join(parts) if parts else "coverage is unreported"
    if unattended:
        return (body.capitalize() + ". Nobody is looking at this, which is what "
                "separates a company that may not have been read yet from one the "
                "market has read and priced.")
    return (body.capitalize() + ". This is watched, so a low price is more likely to "
            "be an opinion than an oversight.")


def screen(verdict_row: dict, register_result: Optional[dict] = None,
           technical: Optional[dict] = None) -> dict:
    """Whether this name is a solid business the market is not attending to.

    Reads components the verdict already computed rather than recomputing any
    lens — the same rule `structure.read` follows — so a name's cheapness here
    is the cheapness the report prints beside it.
    """
    value = _component(verdict_row, "value")
    quality = _component(verdict_row, "quality")
    watch = attention(register_result)
    free_float = _finite(((register_result or {}).get("float") or {}).get("freeFloat"))
    if free_float is None:
        # `ownership.read` puts it under `float`; the raw register does not carry
        # it. Fall back to the inverse of the insider stake when only the raw
        # payload is at hand.
        insiders = _finite((register_result or {}).get("insidersPercentHeld"))
        free_float = (1.0 - insiders) if insiders is not None else None

    missing = [name for name, got in (("value", value), ("quality", quality))
               if got is None]
    if missing:
        return {"available": False, "selected": False,
                "reason": (f"{' and '.join(missing)} did not read for this name, and "
                           f"the screen refuses on a gap rather than selecting on the "
                           f"components that happen to have arrived"),
                "attention": watch}

    cheap = value >= CHEAP_AT
    solid = quality >= SOLID_AT
    tradeable_float = free_float is None or free_float >= MIN_FREE_FLOAT
    selected = bool(cheap and solid and watch["unattended"] and tradeable_float)

    # `currentDrawdown`, NOT `current`. This read the wrong key from the day it
    # was written, so the drawdown was always None and the sentence below that
    # reports it — the context this module's docstring promises a reader, in the
    # paragraph explaining why there is deliberately no momentum FILTER — has
    # never once appeared. `longterm.py` has named it `currentDrawdown` since it
    # was written; nothing compared the two, and a key that is simply absent
    # reads as a company with no drawdown rather than as a typo.
    drawdown = _finite((((technical or {}).get("longTerm") or {})
                        .get("drawdown") or {}).get("currentDrawdown"))

    return {
        "available": True,
        "selected": selected,
        "value": value,
        "quality": quality,
        "cheap": cheap,
        "solid": solid,
        "freeFloat": free_float,
        "tradeableFloat": tradeable_float,
        "attention": watch,
        # CONTEXT, NEVER A CRITERION. See the module docstring: filtering on it
        # would reintroduce the momentum bias the screen exists to escape.
        "drawdown": drawdown,
        "thresholds": {"cheapAt": CHEAP_AT, "solidAt": SOLID_AT,
                       "unattendedHeld": UNATTENDED_HELD,
                       "unattendedAnalysts": UNATTENDED_ANALYSTS},
        "reading": _reading(selected, cheap, solid, value, quality, watch,
                            free_float, tradeable_float, drawdown),
    }


def _reading(selected: bool, cheap: bool, solid: bool, value: float, quality: float,
             watch: dict, free_float: Optional[float], tradeable_float: bool,
             drawdown: Optional[float]) -> str:
    if selected:
        text = (f"The valuation reads {value:.0f} and the accounting screens {quality:.0f}, "
                f"so the business is sound and the price is below what the model makes it "
                f"worth. {watch['reading']}")
        if drawdown is not None and drawdown < -0.15:
            text += (f" It is {abs(drawdown) * 100:.0f}% below its own high, which is why "
                     f"the price family scores it poorly and why the blended score has no "
                     f"opinion — that is the situation this screen exists to surface, not "
                     f"evidence the fall is over.")
        return text

    failed = []
    if not cheap:
        failed.append(f"the valuation reads {value:.0f}, not cheap")
    if not solid:
        failed.append(f"the accounting screens read {quality:.0f}, not solid")
    if not watch["unattended"]:
        failed.append("it is already covered")
    if not tradeable_float:
        failed.append(f"only {(free_float or 0) * 100:.0f}% of the stock is tradeable")
    return ("Not selected: " + "; ".join(failed)
            + ". All of cheap, solid and unattended have to hold together — cheap "
              "without solid is a value trap, and solid without unattended is "
              "already priced.")
