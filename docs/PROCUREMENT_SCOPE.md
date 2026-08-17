# Procurement Intelligence — scope

Decided 2026-08-12. This supersedes the narrower reading of Phase 6 in
`docs/IMPLEMENTATION_PLAN.md`, which was written around vehicles, gold and
property and is too small.

## What this is for

Any purchase a person or a business makes: consumer durables, construction
material, land and property, business and agricultural assets, vehicles of every
fuel type. For each one, three questions:

1. **What does it actually cost me?** — landed cost, not the sticker price
2. **What am I entitled to?** — every subsidy, concession and tax effect, with
   the closed ones named and dated
3. **Which option is cheapest for me?** — compared on landed cost, not on price

## The one rule that shapes everything

**Observed prices and computed costs are different things and are never mixed.**

| | source tier | may enter a cost line | how it is shown |
|---|---|---|---|
| Marketplace / dealer listing | 3 | **no** | badged "unverified, seen on `<date>`" |
| OEM price list, bank rate card | 2 | yes | cited with fetch date |
| CBIC, parivahan, state transport, IGR, RERA | 1 | yes | cited with fetch date |

`CostLine` refuses to construct from a Tier-3 fact
(`backend/core/provenance/sourcing.py`). That is enforced by the type, not by
convention.

**Why not just aggregate prices and report the lowest.** A scraped listing is
stale, usually excludes freight, installation and state levies, and is often not
honoured at checkout. A single authoritative "lowest price" is a number nobody
can honestly state. What *can* be stated is: here are the listings we saw and
when, and here is what each option costs you landed once GST, state levies,
subsidies and tax effects are applied. That is the comparison worth making,
because landed cost is where options actually differ — an EV and a petrol car at
the same sticker price are ₹4.2 lakh apart on the road.

## Where the data comes from: search proposes, rules admit

Decided 2026-08-13.

Pre-storing every rate this needs — thirty-odd states of stamp duty and road
tax, every solar and agri and MSME scheme, every OEM price list — is a
maintenance treadmill nobody keeps current. The road tax table in
`procurement.yaml` covers four states and is already a liability. So the agents
get web search.

Search does not answer the question. Search **proposes a candidate**, and the
rules decide whether it is admitted as a fact.

```
web search  →  CandidateFact  →  admit()  →  SourcedFact  →  CostLine
               (cannot cost)      (rules)     (can cost)
```

`CandidateFact` is a different type from `SourcedFact`, not a flag on it. There
is no way to hand a candidate to `CostLine`, so promotion is the only route
across and promotion runs the checks. Same argument as `Tier3CannotCost`: a rule
enforced by code review survives until the first deadline.

**The five checks, and none of them asks a model anything**
(`backend/core/provenance/admission.py`, rules in `admission.yaml`)

| check | what it refuses | why it is not a judgement call |
|---|---|---|
| deterministic extractor | a number a model read and reported | a model may find the page and say where to look; the figure must be liftable from the same bytes tomorrow |
| unambiguous parse | a bare `5` | five, or five per cent? guessing is how a 500% rate ships |
| plausibility band | 42% stamp duty, an abolished 12% GST slab | catches the extractor that grabbed the phone number or the loan rate |
| tier from domain | "this looks official" | tier comes from a host table; unknown defaults **down** to Tier-3 |
| corroboration by host | one page, or two pages on one site | independence is by host; `www.x` and `x` are one source |

A key with no plausibility band declared is **quarantined, not waved through**.
Unscreened is not the same as safe.

**When a check fails, the line is omitted and the gap is named.** Not a national
average — averaging 5% and 7% gives 6%, which is authoritative-looking and true
nowhere. A `Gap` says which figure is missing, why, and what would fix it. A
missing line a user can see is recoverable; a confidently wrong one is the
failure mode this codebase exists to avoid, and falling back to an average
reintroduces it at exactly the moment the system already knows it is on thin
ice.

The one exception: a Tier-3 candidate that a deterministic extractor lifted and
that is plausible is admitted as **context only** — a real fact at
`Tier.AGGREGATOR`, which `CostLine` still refuses by type. It can be shown,
badged, beside the breakdown. It cannot be added up. A **model-authored figure
is never context only**: badging does not cure a hallucination, it only gives it
a place on the page.

**The extractors** (`backend/procurement/extract.py`)

The gate is only as good as the thing reading the page, so four refusals live
there too:

- **The extractor names itself.** `extracted_by` is set inside the extractor and
  is never a parameter. A caller cannot label a model's guess `html_table_cell`
  and walk it past a gate that only compares strings.
- **Headers, never indices.** `rows[3][2]` keeps parsing cleanly after someone
  inserts a column, and starts returning a different number with no error
  anywhere.
- **Ambiguity is refused.** A label appearing twice with two different figures
  yields nothing. Taking the first is a guess wearing a deterministic costume,
  and the more dangerous kind — it arrives with a provenance trail.
- **The raw page text is kept.** `raw_value` is `"5 per cent"`, not `0.05`, so
  admission re-parses in the open and an auditor sees what the page said.

An empty cell is not a zero — a blank means the page did not say, and reading it
as 0% invents a road-tax-exempt state out of a formatting artefact. An AST
ratchet stops any `agents/`, `tools/` or `orchestrator/` module building a
`CandidateFact` by hand, which would otherwise defeat the gate while passing
every one of its checks.

**Latency: the network is never on the critical path**
(`backend/procurement/gather.py`)

- `resolve(keys, cache, today)` — answer time. **No `search` parameter exists.**
  Not a default of `None`, not a flag. The only thing that can fail is a
  dictionary lookup, and that is a property of the signature rather than of
  anyone's discipline. Same line AGT-012 takes with `FreshnessCache`.
- `sweep(queries, cache, search, today)` — background. The only thing that
  reaches the network, and through an injected function, so the costing path
  never names a search backend.

Stale serves; missing does not. A cached fact past its TTL comes back with its
badge — a labelled 40-day-old GST rate beats an error page. A failed sweep never
evicts a good cached fact, because one bad fetch must not turn a working answer
into a gap.

## Two dimensions, not one

### Goods families
Each needs its own HSN/GST mapping, its own cost lines and its own scheme set.

- **Home and consumer durables** — appliances, electronics, furniture, rooftop
  solar. PM Surya Ghar, BEE star ratings, state solar schemes.
- **Construction and land** — cement, steel, land, property. Stamp duty, circle
  rates, RERA, s.50C and s.56(2)(x), PMAY.
- **Business and agricultural assets** — machinery, tractors, farm equipment,
  commercial vehicles, MSME plant. PM-KUSUM, agri-machinery schemes, MSME
  capital subsidy. Where ITC and depreciation actually pay.
- **Vehicles** — all fuel types, two-wheelers and commercial, not only EVs.

### Buyer profile
**The same item gives a different answer to a different buyer**, and this cuts
across every family above rather than sitting beside them.

- **Government employee** — 14% employer NPS in both regimes rather than 10%,
  LTC, departmental vehicle and housing advance schemes, CGHS.
- **Salaried private sector (IT and others)** — employer-provided asset versus
  own purchase, perquisite valuation, LTA, corporate purchase programmes.
- **Self-employed and professional** — depreciation, s.44ADA interaction,
  business-use apportionment.
- **GST-registered business** — input tax credit, but blocked on passenger
  vehicles under s.17(5) except for four narrow uses.

An engine that models only the item will tell a government employee and a
freelancer the same thing about the same laptop, and be wrong for at least one
of them.

## Quote teardown: two totals, never one

`backend/procurement/quote_teardown.py` compares the buyer's actual quotation
against the computed landed cost. It reports **two separate figures**:

- **overcharged** — a statutory line disagrees with the statute. Defensible,
  arguable in writing.
- **negotiable** — a charge with no statutory basis. Legal, and open to
  discussion.

Summing them would hand a buyer one number to take into a showroom, part of
which they will be told — correctly — that they agreed to. The argument then
collapses and takes the defensible half with it.

Padding hides in the naming, so matching is longest-term-first: "RTO
Registration Charges" contains both `rto` and `registration`, and the two are
compared against a state road tax and a ₹600 fee respectively.

Deltas never go negative. An under-charged line must not net off a real
overcharge somewhere else in the same quote.

**TCS is not a cost.** Under s.206C(1F) it is the buyer's own tax collected
early — creditable, visible in Form 26AS. Listed beside road tax it makes the
on-road price look higher than the money they are actually out, and almost
nobody claims it back. It is checked at 1% of the *entire* consideration above
₹10 lakh, not of the excess.

**Silence is not approval.** A line the engine cannot price is reported as
UNCHECKED with a coverage statement, never omitted — "three issues found" reads
as "everything else is fine".

## What this deliberately does not do

- **No price prediction.** PRC-005 is a ledger of dated, sourced facts that
  change cost — policy cliffs, GST effective dates, the 31 March depreciation
  boundary. Observed seasonal patterns are labelled as historical with the years
  observed. Nothing forecasts a price movement.
- **No investment or securities advice.** Out of scope and refused (AGT-006).
- **No opinion on whether a locality will appreciate.**
- **No claim of national coverage it does not have.** Road tax currently covers
  four states and an unlisted state raises rather than averaging. Coverage is
  stated, never implied.
