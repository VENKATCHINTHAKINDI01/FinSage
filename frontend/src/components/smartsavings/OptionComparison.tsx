import { AlertTriangle, HelpCircle, Info, ShoppingBag } from 'lucide-react';

import { Money, type Provenance } from '../shared/Money';

/**
 * Comparing purchase options — PRC-009.
 *
 * Ranked by LANDED COST, which is the whole point
 * ------------------------------------------------
 * Sticker price is where options look alike and landed cost is where they
 * actually differ: an EV and a petrol car at the same ex-showroom price are
 * lakhs apart on the road, because GST is 5% against 40% and several states
 * charge no road tax on a battery vehicle. A comparison ordered by sticker
 * price is ordering by the one number that does not decide anything.
 *
 * Three things kept structurally apart
 * -------------------------------------
 * **Computed costs** — every line a `CostLine` from an official or manufacturer
 * source, rendered through `Money` so a figure with no provenance cannot
 * appear at all.
 *
 * **Observed listings** — what a marketplace showed on a date. Badged
 * unverified, shown in their own section, and NEVER added to anything. This
 * component does no arithmetic whatsoever: every total displayed comes from
 * the backend, so there is no code path in which a listing could reach one.
 *
 * **Gaps** — lines that could not be computed, named with what would fix them.
 * A breakdown that silently drops the road tax for an uncovered state looks
 * identical to one where the road tax is genuinely nil.
 *
 * Closed windows are shown, not filtered
 * ---------------------------------------
 * "80EEB would have given you ₹1,50,000 but the sanction window closed on
 * 31 March 2023" is more useful than silence, and it is the sentence that makes
 * a user believe the rest of the output. Filtering closed schemes out is how a
 * tool ends up looking empty when it is actually well informed.
 *
 * Signals are dated facts
 * ------------------------
 * Rendered from the ledger's own sentences (PRC-005). This component does not
 * compose a sentence about timing, so it cannot compose a forecast.
 */

export interface CostLineView {
  label: string;
  display: string;
  is_deduction: boolean;
  source: {
    source_url: string;
    tier_label: string;
    fetched_on: string;
    as_of: string;
    may_drive_a_cost_line: boolean;
    badge?: string;
  };
  provenance?: Provenance | null;
}

export interface GapView {
  key: string;
  sentence: string;
}

export interface ListingView {
  seller: string;
  display: string;
  url: string;
  seen_on: string;
}

export interface OptionView {
  id: string;
  item: string;
  /** Pre-formatted by the backend. Never recomputed here. */
  ex_showroom_display: string;
  on_road_display: string;
  landed_display: string;
  /** Decimal string, for ordering only — never rendered. */
  landed_sort_key: string;
  lines: CostLineView[];
  gaps: GapView[];
  listings: ListingView[];
  notes: string[];
}

export interface ClosedWindowView {
  name: string;
  message: string;
  closed_on: string | null;
}

export interface SignalView {
  kind: string;
  sentence: string;
  is_a_forecast: boolean;
}

export interface OptionComparisonProps {
  options: OptionView[];
  closedWindows?: ClosedWindowView[];
  signals?: SignalView[];
  /** Benefits that apply but whose amount is unverified or unknown. */
  unquantified?: string[];
}

/**
 * Ordering only. Deliberately not a currency parse — `landed_sort_key` is a
 * plain decimal string the backend supplies for exactly this purpose, so that
 * nothing here has to interpret a rupee display string and get it wrong on a
 * lakh separator.
 */
function byLandedCost(a: OptionView, b: OptionView): number {
  const left = Number(a.landed_sort_key);
  const right = Number(b.landed_sort_key);
  if (Number.isNaN(left) || Number.isNaN(right)) return 0;
  return left - right;
}

export function OptionComparison({
  options,
  closedWindows = [],
  signals = [],
  unquantified = [],
}: OptionComparisonProps) {
  const ranked = [...options].sort(byLandedCost);

  return (
    <div className="space-y-6" data-testid="option-comparison">
      <p className="text-[12px] text-ink-soft">
        Ranked by what each option costs you once GST, state levies, subsidies
        and tax effects are applied — not by the sticker price, which is where
        options look alike.
      </p>

      {ranked.map((option, index) => (
        <section
          key={option.id}
          data-testid={`option-${option.id}`}
          data-rank={index + 1}
          className="rounded-lg border border-line bg-surface p-4"
        >
          <header className="flex items-baseline justify-between gap-3">
            <h3 className="text-[14px] font-medium text-ink">{option.item}</h3>
            <span className="text-[11px] text-ink-soft">
              Ex-showroom {option.ex_showroom_display} · On the road{' '}
              {option.on_road_display}
            </span>
          </header>

          <p className="mt-1 text-[13px] text-ink">
            <span className="text-ink-soft">Landed cost </span>
            <span data-testid={`landed-${option.id}`} className="tabular-nums font-medium">
              {option.landed_display}
            </span>
          </p>

          <ul className="mt-3 space-y-1">
            {option.lines.map((line) => (
              <li
                key={line.label}
                className="flex items-center justify-between gap-3 text-[12px]"
              >
                <span className="text-ink-soft">
                  {line.is_deduction ? 'Less: ' : ''}
                  {line.label}
                </span>
                <span className="flex items-center gap-2">
                  <Money
                    display={line.display}
                    provenance={line.provenance}
                    label={line.label}
                  />
                  <span className="text-[10px] text-ink-soft">
                    {line.source.as_of}
                  </span>
                </span>
              </li>
            ))}
          </ul>

          {option.gaps.length > 0 && (
            <div
              data-testid={`gaps-${option.id}`}
              className="mt-3 rounded border border-warning/40 bg-warning/10 p-2"
            >
              <p className="flex items-center gap-1 text-[11px] font-medium text-warning">
                <AlertTriangle size={12} aria-hidden />
                Not included in the figures above
              </p>
              <ul className="mt-1 space-y-1">
                {option.gaps.map((gap) => (
                  <li key={gap.key} className="text-[11px] text-ink-soft">
                    {gap.sentence}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {option.listings.length > 0 && (
            <div
              data-testid={`listings-${option.id}`}
              className="mt-3 rounded border border-line bg-canvas p-2"
            >
              <p className="flex items-center gap-1 text-[11px] font-medium text-ink-soft">
                <ShoppingBag size={12} aria-hidden />
                Listings we saw — unverified, and not part of any total above
              </p>
              <ul className="mt-1 space-y-1">
                {option.listings.map((listing) => (
                  <li
                    key={`${listing.seller}-${listing.seen_on}`}
                    data-testid="listing-row"
                    className="flex items-center justify-between gap-3 text-[11px]"
                  >
                    <span className="text-ink-soft">{listing.seller}</span>
                    <span className="flex items-center gap-2">
                      <span className="tabular-nums text-ink">{listing.display}</span>
                      <span className="rounded bg-warning/15 px-1 text-[10px] text-warning">
                        unverified · seen {listing.seen_on}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {option.notes.map((note) => (
            <p key={note} className="mt-2 flex gap-1 text-[11px] text-ink-soft">
              <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
              {note}
            </p>
          ))}
        </section>
      ))}

      {unquantified.length > 0 && (
        <section
          data-testid="unquantified"
          className="rounded-lg border border-line bg-surface p-3"
        >
          <p className="flex items-center gap-1 text-[12px] font-medium text-ink">
            <HelpCircle size={13} aria-hidden />
            Benefits that apply but are not counted in the figures
          </p>
          <ul className="mt-1 space-y-1">
            {unquantified.map((line) => (
              <li key={line} className="text-[11px] text-ink-soft">
                {line}
              </li>
            ))}
          </ul>
        </section>
      )}

      {closedWindows.length > 0 && (
        <section
          data-testid="closed-windows"
          className="rounded-lg border border-line bg-surface p-3"
        >
          <p className="text-[12px] font-medium text-ink">
            Schemes that have closed
          </p>
          <p className="mt-0.5 text-[11px] text-ink-soft">
            Shown rather than hidden. Knowing a window shut, and when, is more
            useful than an empty list.
          </p>
          <ul className="mt-2 space-y-1">
            {closedWindows.map((window) => (
              <li
                key={window.name}
                data-testid="closed-window"
                className="text-[11px] text-ink-soft"
              >
                {window.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      {signals.length > 0 && (
        <section
          data-testid="signals"
          className="rounded-lg border border-line bg-surface p-3"
        >
          <p className="text-[12px] font-medium text-ink">Dates that change the cost</p>
          <p className="mt-0.5 text-[11px] text-ink-soft">
            Scheme windows and statutory boundaries. Nothing here is a view on
            where prices are going.
          </p>
          <ul className="mt-2 space-y-1">
            {signals.map((signal) => (
              <li
                key={signal.sentence}
                data-testid="signal"
                className="text-[11px] text-ink-soft"
              >
                {signal.sentence}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
