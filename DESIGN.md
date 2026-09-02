# Design

<!-- impeccable:design-schema 1 -->

Written from the built v2 surface, 29 August 2026. It describes what shipped; it
is not a wish list. Anything here that the code contradicts is a bug in this
file.

## The thesis

**A research desk that ranks evidence, not companies.**

The category default is a dashboard whose largest element is a verdict. This
refuses that permanently — `PRODUCT.md` constraint 1, guarded by two pytest
suites. So the largest element is the ticker, the second largest is the question
each lens is answering, and the reader's own eye does the combining.

The whole v2 problem was that refusing a verdict had been confused with refusing
*hierarchy*. Every finding arrived at the same weight, so a page that would not
tell you what to think also would not tell you where to start.

## What was wrong, measured

Taken on the default view (AAPL, Trend tab) before any change:

| | v1 | v2 |
|---|---|---|
| Distinct font sizes rendered | 16, with 272 of 402 nodes inside a 3px band | 7, each step ≥15% from its neighbour |
| Text in the de-emphasis grey | 54% | 36% |
| Section headings | `h2` at **10.88px**, below the 12px body it introduced | 22px |
| Prose ≥12 words under 13px | many | 0 |
| Interactive elements under 24×24 | 48 of 74 | 0 of 59 desktop, 1 of 60 mobile |
| Longest line | 96ch at 673px, worse on desktop | capped at 40rem / ~68ch |
| Identical card containers | 71 | three differentiated strata |
| Desktop page height | 8,415px | 7,034px |

A second pass took the same treatment to every remaining panel and to the copy.
Measured per tab, in Guided, on one ticker:

| | before that pass | after |
|---|---|---|
| Words visible on the Trend tab | 2,476 | 1,975 |
| Words visible, Portfolio tab | 1,437 | 936 |
| Words one click away (per tab) | ~550 | ~1,100 |
| Tab height, Trend | 7,128px | 6,073px |

The shared header is what made this necessary: the synthesis (563 words) and the
pre-trade panel (517 words) sit above **every** tab, so a reader met 1,080 words
and 2,600px of the same prose on each of the seven.

**The height rows settle the "less text vs. more readable" argument.** Not one
sentence was deleted across either pass, the type got bigger, and both the page
and every tab got shorter. Progressive disclosure did that, not cutting.

## Colour

Two systems that must never blend.

**Identity** — which model is speaking. Structural, always on, says nothing
about the company. A lens is its colour whether its reading is excellent or
catastrophic.

| | |
|---|---|
| `flow` | `#2FBFA4` |
| `trend` | `#6B9BFF` |
| `value` | `#E8B44C` |
| `quality` | `#C9A227` |
| `thesis` | `#A78BFA` |

**Tone** — what the server concluded. Arrives from `explain.tone` and from
nowhere else. A component that picks one of these from the sign of a number has
re-litigated a judgement Python already made, which is the bug class §14 spent a
whole audit removing.

| | |
|---|---|
| `acc` (good) | `#35C4A8` |
| `dist` (bad) | `#FF6B6B` |
| `warn` | `#F2C14E` |

Before v2 these overlapped: the flow lens's teal and the "accumulation" verdict
were one token doing two jobs, so a lens name and a conclusion rendered
identically and neither read as meaningful.

**Strata and text.** Colour commits at region scale — a lens hue owns a tinted
header field, not a 2px strip of trim.

| Ground | | | Text | | |
|---|---|---|---|---|---|
| `ink` | `#080C10` | page | `chalk` | `#E7EEF5` | headings, figures |
| `panel` | `#111820` | standard surface | `body` | `#C3CFDC` | running prose |
| `raised` | `#161F29` | above the page | `ash` | `#8496A9` | captions, units |
| `sunken` | `#0C1116` | wells inside a panel | `faint` | `#63748A` | furniture |
| `rule` / `ruleSoft` | `#1E2A36` / `#18222C` | hairlines | | | |

`body` is the v2 addition and it carries most of the change. v1 had two text
colours, and 54% of every screen was the dimmer one — when more than half a page
is de-emphasised, nothing is emphasised.

Dark, and not by category habit: this is read at a desk, at length, beside
filings and a broker tab, in the evening as often as not.

## Type

`Inter` for prose, `IBM Plex Mono` for measured numerals. Mono is for data, never
as a costume for "technical" — v1 also spent it on headings, buttons and tab
labels, and v2 took it back.

| Token | Size | Use |
|---|---|---|
| `micro` | 11px | units, footnotes, table headers, `.eyebrow` |
| `meta` | 13px | captions, table cells, secondary prose |
| `base` | 15px | running prose. The body default. |
| `lead` | 17px | the one sentence that carries a finding |
| `h3` | 17px | subsection |
| `h2` | 22px | section |
| `figure` | 24px | a headline number |
| `h1` | 28px | the ticker |

**The lead-line rule.** A long finding opens at `lead` and continues at `base`,
so a reader who stops after one line still holds the finding. It is the cheapest
progressive disclosure available and it costs no interaction.

**`.eyebrow` is a field label and never a heading.** It names the value directly
beneath it. An `h2` wearing it is the inverted hierarchy v2 exists to fix.

**Measure.** `prose-col` caps at `40rem`; `prose-col-wide` at `46rem`.

## Components

**Surfaces are three, not one.** `panel` for a finding, `sunken` for a well
inside one (quoted figures, working, raw data), `raised` for something floating
(controls, popovers). 71 identical containers marked where a box started and not
what kind of thing was in it.

**Lens chips.** Four lenses, four words, four tone dots, on a fixed grid. The one
piece of at-a-glance this app allows itself, agreed with the owner on 29 August
2026. Never summed, averaged, counted or ordered by strength — three greens and a
red stay three greens and a red, and the synthesis says in sentences what a score
cannot. They wrap rather than truncate: "Above model range" clipped to "Above
mod…" is not a shorter verdict, it is a different one.

**Blocks are typed, not uniform.** `finding` for what the app is telling you,
`quiet` (recessed) for what it is admitting. Deliberately two values: a third
would be a severity scale, and a severity scale over blind spots is a ranking of
how bad the gaps are — the composite this app refuses, arriving through a font
size.

**Disclosures start closed and name what is inside.** The lens-agreement working
runs to ~200 words of statistics and put Cohen's kappa in front of a reader who
had not finished the paragraph about their company. Closed, with κ on the summary
line so it is not a mystery box.

**`Explainer` — a long explanation with its point on the outside.** The single
biggest source of overload: fifty paragraphs across the panels ran past ninety
characters, one to ninety-six *words*, every one permanently open, each
explaining a method to a reader who had not decided they cared about the method.

Its `summary` must be a **claim, not a label**. "Seven columns are not seven
tests" is worth opening; "About this table" is a hidden paragraph with extra
steps. The summary is the only part most readers will ever see, so it carries
the meaning of the section on its own.

**What may collapse is decided by meaning, not by length.** In the pre-trade
panel, conditions that *fired* never collapse — they are why the panel exists.
What collapses is the qualifying material (ordinary for this market, never
tested, withheld for want of a base rate), and only because the summary states
the qualification itself: *"never tested — which is not the same as clear"*
carries the point while shut. In the synthesis, the blind-spot list collapses
because its title already states its claim.

The summary text must live **inside** the `<summary>` element. Anywhere else in
the `<details>` it renders only when open — exactly when it is no longer needed —
and the collapsed state reverts to a bare label. Caught by reading the rendered
text of a closed group, not by reading the source.

**Info button, 24×24.** The app's central promise is that every number explains
itself; v1 drew the affordance carrying it at 14px. The ring grew, not the glyph,
so a dense table row still reads as a table row.

**Icons** are lucide, one stroke weight. No emoji, no unicode glyphs.

## Accessibility

Not a conformance claim — these are the things v2 actually fixed.

- **Target size.** 48 of 74 elements were under 24×24. Now 0 on desktop.
- **Declared ARIA patterns now keep their contracts.** Both tablists and both
  radiogroups declared roles and implemented none of the keyboard behaviour those
  roles promise. A screen reader announcing "tab, 2 of 7" where arrow keys do
  nothing is worse than a plain button. Roving tabindex, arrow keys, Home/End,
  `aria-controls`, and a real `role="tabpanel"`.
- **The `Explain` popover is no longer `role="tooltip"`.** It is three labelled
  paragraphs with a heading and a close button, opened by a click. A tooltip is a
  short non-interactive label.
- **Contrast.** Eight sites used `text-ash` at 40–70% alpha, composited to
  2.2–3.2:1. Gone with the ladder.

  **The palette is now checked rather than asserted, and the assertion was
  wrong.** This read "Base palette clears AA: `ash` on `panel` is 4.82:1, `body`
  8.9:1". Both figures were understated — the real ones are 5.88 and 11.30 — and
  more to the point, the token it did not quote was the one that failed.
  `faint` was described here as furniture, but `.eyebrow` sets every field label
  in it and the footer disclaimer is set in it too: twenty-one sites of real
  text, at 3.48–4.11:1 against the four grounds. Lightened to `#7387A0`, which
  clears 4.52–5.33 and stays a clear step below `ash`.

  | on | `ink` | `panel` | `raised` | `sunken` |
  |---|---|---|---|---|
  | `chalk` | 16.77 | 15.27 | 14.22 | 16.21 |
  | `body` | 12.41 | 11.30 | 10.52 | 11.99 |
  | `ash` | 6.46 | 5.88 | 5.48 | 6.25 |
  | `faint` | 5.33 | 4.85 | 4.52 | 5.15 |

  Rule 8 in `check_frontend.mjs` recomputes this table from
  `tailwind.config.ts` on every build, so the claim cannot drift from the
  tokens again. Contrast is arithmetic on the config and needs no browser.
- **iOS zoom.** Inputs are 16px below `sm`. Under that, iOS zooms on focus and
  does not zoom back.
- **Browser surfaces** are themed: selection, caret, scrollbars, focus ring.
- **`aria-controls` only where the target exists.** Every disclosure here renders
  its content conditionally, so a permanent reference points at an id that is not
  in the document — 25 of them were, on one screen. `aria-expanded` carries the
  state; a reference to nothing is worse than none, because assistive technology
  offers a jump that goes nowhere.
- **Two tablists, two names.** Both announced themselves as "Lenses", so a
  screen-reader user heard the same group name twice with no way to tell which
  one they were in. The inner one is "Time horizon" now.

**Verified by walking the real tab order**, not by reading the markup: 64
focusable elements, zero without an accessible name, zero without a visible
focus style, zero positive `tabindex`, zero dangling `aria-controls`, and all
four roving groups at exactly one tab stop. Arrow keys and Home move both
tablists and both radiogroups.

**Automated audit, 1 September 2026.** axe-core, all WCAG 2.0/2.1 A and AA
rules, run against the live page in every one of the eight tabs with a ticker
loaded: **zero violations**, 30-48 passes per tab. Two things it found and that
are now fixed:

- **1,464 unlabelled images on one tab.** Recharts stamps `role="img"` on every
  scatter symbol, so the anomaly chart alone put that many into the
  accessibility tree — a screen reader announcing "image" fourteen hundred
  times, which is worse than announcing nothing. The rendering is now
  `aria-hidden`; the panel already states its finding in prose, and that prose
  stays outside the hidden subtree.
- **The text palette did not clear AA**, covered above.

To repeat it: `axe-core` is a devDependency; copy `node_modules/axe-core/
axe.min.js` into `public/`, load it from the page (the CSP allows same-origin
scripts), and call `axe.run`. Delete it afterwards — it is a 580 KB audit tool,
not an asset.

**One false positive worth naming**, because it cost three rounds of chasing.
`getComputedStyle` through a CDP bridge can return a *stale* value for an
element that has just changed state, and the submit button changes from
`disabled:bg-rule` to `bg-tech` as soon as a ticker is typed. Both axe and a
hand-rolled contrast walker read the stale colours and reported the primary
action at 3.05:1. It renders blue at 7.25:1 — verified against the pixels in a
screenshot, which is the only ground truth when the two disagree.

**Still not done:** nobody has listened to this with a screen reader. The
keyboard contract is implemented and measured, the automated rules pass, and how
it *sounds* is still untested — an automated pass is a floor, not a substitute.

## The rules are enforced, not just written

`npm run check:frontend` enforces eight of them, and each describes a bug
that was really in this codebase:

1. A heading wearing `.eyebrow` — the inverted hierarchy.
2. Prose at `text-micro` (11px) — caught by `leading-relaxed`, which marks a
   paragraph.
3. Arbitrary font sizes outside the scale, allowlisting only the iOS 16px input
   rule and the `.eyebrow` definition itself.
4. Alpha text colours (`text-chalk/80`) — the contrast bug.
5. A `tablist` or `radiogroup` declared without `onKeyDown` and a roving
   `tabIndex`.
6. A coloured side stripe (`border-l-2`).
7. Sign-based tone colouring over a documented per-file budget — in a
   Tailwind class OR an inline style, since the first version of the rule saw
   only the former and was hiding two real sites in `LongTermPanel` and one in
   `EventStudyPanel`.
8. A text token that does not clear WCAG AA against every ground, recomputed
   from `tailwind.config.ts` rather than trusted.

Comments are stripped before the greps — rule 7 fired on its own explanation the
first time it ran, because `LongTermPanel`'s docstring quotes the expression it
forbids. Each rule was verified to actually fail by breaking it on purpose and
watching the build reject it.

If a rule fires on something legitimate, widen it or extend its allowlist **with
the reason**. Do not delete the check: a rule nobody trusts protects nothing, and
a rule nobody has seen fail is a rule nobody should trust.

## Copy

Plain words where a plain word exists, and the jargon kept where it is the real
name of the thing. An audit of rendered text found only seven genuinely opaque
terms — most `DCF` / `DDM` / `percentile` hits were variable names, and the rail
already renders `DCF` as "cash-flow model". `Mean CAR` became `Mean abnormal
return`; `RSI`, `ADX` and `MFI` stayed, because they are the conventional labels
and each already carries an info button.

**A third pass cut, rather than disclosed.** The owner revised `PRODUCT.md`
constraint 7 on 29 August 2026 after the second pass still read as overwhelming.
Measured before that cut: **2,294 words of prose against 174 words of data on one
tab — thirteen words of explanation per word of number** — and the first control
inside a tab sat 4,300px down.

What went: the app arguing for its own methodology. The 239-word statistics
block behind the lens-agreement figure, the 96-word explanation of why four
panels count as two sources, the 100-word "how to read this" in the header, the
122-word `action` printed beside the implied-growth figure. All of it true, all
of it now in `RESEARCH_ROADMAP.md` and the field manual, both linked.

What stayed, and may never go: every number and the base rate beside it, every
null result and refusal, "an empty panel is not a clean bill of health", every
tone, and "not investment advice".

| | before | after |
|---|---|---|
| Prose on the Trend tab | 2,294w | 1,552w |
| Prose per word of data | 13.2 : 1 | 9 : 1 |
| Longest single block | 239w | 52w |
| Page height, Trend | 11,166px | 9,775px |

**The two panels above every tab now collapse to their conclusion.** The
synthesis and the pre-trade panel are the only things a reader meets on all
eight tabs, so whatever they show by default is shown eight times.

The synthesis dropped its per-lens grid entirely — that was a *duplicate*, not a
cut: the confluence rail directly above already names each lens, its verdict and
a sentence of detail. Printing the same four verdicts again cost 220 words and
900 pixels, seven times over. What is left is what only that panel can say.

| | before | after |
|---|---|---|
| Synthesis | 372w / 1,898px | **99w / 432px** |
| Pre-trade | 107w / 642px | 104w / 622px |
| Trend tab height | 9,775px | **8,289px** |

**What may never collapse.** A summary that folds to a bare title is a hidden
paragraph; each of these folds to its own answer. So the agreement sentence
stays outside the synthesis disclosure, the fired conditions never collapse in
the pre-trade panel, and "an empty panel is not a clean bill of health" is
always in the open — folding that one would be the exact bug that panel exists
to prevent, arriving through a layout decision.

The disclosure handle is built from what is actually inside it, so it can never
offer "where they conflict" on a company that has none.

**The tab bar is sticky**, which is the structural half of the same complaint.
The reading order — summary, then objections, then lenses — is the argument the
app is making and moving the tabs above it would break that. Sticking them keeps
the order and still puts every tool one click from any scroll position.

Rules that survived the pass:

- Expand an acronym unless it is the column's real name and has an `Explain`.
- Lead with the claim, not the method. "A shortlist, not a verdict" before the
  paragraph about how the shortlist is built.
- Cut filler, never a caveat or a number. Where a sentence is long because it is
  carrying a hedge, it stays; where it is long because it was badly written, it
  goes.
- Second person over passive. "Your holdings stay in this browser", not "the
  list is retained client-side".

## Motion

One authored moment: `animate-rise`, 260ms, `cubic-bezier(0.22,1,0.36,1)`, on
panels as they arrive. A pending lens pulses its own rule at the same rate its
panel skeleton does, so a slow engine reads as slow rather than broken.
Everything respects `prefers-reduced-motion`.

## What this design may not do

Inherited from `PRODUCT.md` and repeated here because a visual system is exactly
where they get broken by accident.

1. No composite verdict, in any visual form — no count, badge, ring, meter,
   gauge, ordering, or size difference that implies one lens outranks another.
2. Colour by `explain.tone` only. Six documented sign-based exceptions survive
   where Python has no interpretation to offer.
3. Absence never renders as a pass. There is no green tick in the pre-trade
   panel because there is no pass state to draw.
4. Full mode may not be degraded to serve Guided.
5. Explanations may be restructured or progressively disclosed. They may not be
   deleted.
