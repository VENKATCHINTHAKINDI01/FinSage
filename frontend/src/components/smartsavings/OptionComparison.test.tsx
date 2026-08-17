/**
 * PRC-009 — the comparison UI.
 *
 * Three invariants carry this component, and each one is a way the display
 * could quietly disagree with the engine behind it: options must rank by
 * landed cost, an observed listing must never reach a total, and a gap must
 * never be silently dropped.
 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { OptionComparison, type OptionView } from './OptionComparison';
import type { Provenance } from '../shared/Money';

const today = new Date().toISOString().slice(0, 10);

const sourced: Provenance = {
  citation: 'CBIC · GST 2.0 · 22 September 2025',
  fy: '2026-27',
  act: 'CGST Act, 2017',
  section: '9',
  legacy_section: null,
  rule_id: 'gst@fy_2026_27',
  verified_on: today,
  source_urls: ['https://cbic.gov.in/'],
};

function option(over: Partial<OptionView> = {}): OptionView {
  return {
    id: 'petrol',
    item: 'Petrol hatchback',
    ex_showroom_display: '₹10,00,000',
    on_road_display: '₹14,60,000',
    landed_display: '₹14,60,000',
    landed_sort_key: '1460000',
    lines: [
      {
        label: 'GST at 40%',
        display: '₹4,00,000',
        is_deduction: false,
        source: {
          source_url: 'https://cbic.gov.in/',
          tier_label: 'official',
          fetched_on: today,
          as_of: `as of ${today}`,
          may_drive_a_cost_line: true,
        },
        provenance: sourced,
      },
    ],
    gaps: [],
    listings: [],
    notes: [],
    ...over,
  };
}

const ev = option({
  id: 'ev',
  item: 'Electric hatchback',
  ex_showroom_display: '₹10,00,000',
  on_road_display: '₹10,50,000',
  landed_display: '₹10,50,000',
  landed_sort_key: '1050000',
});

// ── ranked by landed cost, which is the whole point ────────────────────────

describe('ranking', () => {
  it('orders by landed cost, not by the sticker price', () => {
    // Identical ex-showroom. A comparison ordered by sticker price would call
    // these equal, which is the one number that decides nothing.
    render(<OptionComparison options={[option(), ev]} />);
    const sections = screen.getAllByTestId(/^option-(petrol|ev)$/);
    expect(sections.map((s) => s.dataset.testid)).toEqual([
      'option-ev',
      'option-petrol',
    ]);
    expect(sections[0]).toHaveAttribute('data-rank', '1');
  });

  it('does not reorder when the sort key is unusable', () => {
    // Better a stable order than a confidently wrong one.
    render(
      <OptionComparison
        options={[option({ landed_sort_key: 'n/a' }), { ...ev, landed_sort_key: '' }]}
      />,
    );
    const sections = screen.getAllByTestId(/^option-(petrol|ev)$/);
    expect(sections[0].dataset.testid).toBe('option-petrol');
  });

  it('renders the landed cost the backend supplied, unmodified', () => {
    render(<OptionComparison options={[ev]} />);
    expect(screen.getByTestId('landed-ev')).toHaveTextContent('₹10,50,000');
  });
});

// ── listings are shown, never totalled ──────────────────────────────────────

describe('observed listings', () => {
  const withListing = option({
    listings: [
      {
        seller: 'A marketplace',
        display: '₹9,40,000',
        url: 'https://marketplace.example/x',
        seen_on: '2026-08-01',
      },
    ],
  });

  it('badges a listing as unverified with the date it was seen', () => {
    render(<OptionComparison options={[withListing]} />);
    const row = screen.getByTestId('listing-row');
    expect(within(row).getByText(/unverified/)).toBeInTheDocument();
    expect(within(row).getByText(/seen 2026-08-01/)).toBeInTheDocument();
  });

  it('says out loud that listings are not part of any total', () => {
    render(<OptionComparison options={[withListing]} />);
    expect(
      screen.getByText(/not part of any total above/i),
    ).toBeInTheDocument();
  });

  it('a listing changes nothing about the displayed totals', () => {
    // The load-bearing assertion. The component does no arithmetic at all, so
    // there is no path by which a marketplace price could reach a total — this
    // proves it by rendering with and without one.
    const { unmount } = render(<OptionComparison options={[option()]} />);
    const without = screen.getByTestId('landed-petrol').textContent;
    unmount();

    render(<OptionComparison options={[withListing]} />);
    expect(screen.getByTestId('landed-petrol')).toHaveTextContent(without!);
  });
});

// ── gaps are never silently dropped ─────────────────────────────────────────

describe('gaps', () => {
  it('names what could not be computed and why', () => {
    render(
      <OptionComparison
        options={[
          option({
            gaps: [
              {
                key: 'road_tax.TR',
                sentence:
                  'road_tax.TR is not included: no rate has been gathered for it. Gather it from the state transport department.',
              },
            ],
          }),
        ]}
      />,
    );
    const box = screen.getByTestId('gaps-petrol');
    expect(within(box).getByText(/road_tax.TR is not included/)).toBeInTheDocument();
    expect(screen.getByText(/Not included in the figures above/i)).toBeInTheDocument();
  });

  it('shows no gap panel when there is nothing missing', () => {
    render(<OptionComparison options={[option()]} />);
    expect(screen.queryByTestId('gaps-petrol')).not.toBeInTheDocument();
  });
});

// ── every figure goes through Money ─────────────────────────────────────────

describe('provenance', () => {
  it('a cost line with no provenance renders as unsourced rather than as a number', () => {
    render(
      <OptionComparison
        options={[
          option({
            lines: [
              {
                label: 'Mystery charge',
                display: '₹12,000',
                is_deduction: false,
                source: {
                  source_url: '',
                  tier_label: 'unverified aggregator',
                  fetched_on: today,
                  as_of: `as of ${today}`,
                  may_drive_a_cost_line: false,
                },
                provenance: null,
              },
            ],
          }),
        ]}
      />,
    );
    expect(screen.getByTestId('unsourced-figure')).toBeInTheDocument();
    expect(screen.queryByText('₹12,000')).not.toBeInTheDocument();
  });

  it('shows the as-of date beside each computed line', () => {
    render(<OptionComparison options={[option()]} />);
    expect(screen.getByText(`as of ${today}`)).toBeInTheDocument();
  });
});

// ── closed windows and signals ──────────────────────────────────────────────

describe('closed windows', () => {
  it('shows them rather than filtering them out', () => {
    render(
      <OptionComparison
        options={[option()]}
        closedWindows={[
          {
            name: '80EEB',
            message:
              'Interest on electric vehicle loan: would have given you up to ₹1,50,000, but the window closed on 31 March 2023.',
            closed_on: '2023-03-31',
          },
        ]}
      />,
    );
    expect(screen.getByTestId('closed-window')).toHaveTextContent('31 March 2023');
    expect(screen.getByText(/more useful than an empty list/i)).toBeInTheDocument();
  });
});

describe('signals', () => {
  it('renders the ledger sentences and disclaims forecasting', () => {
    render(
      <OptionComparison
        options={[option()]}
        signals={[
          {
            kind: 'policy_cliff',
            sentence:
              'PM-Surya Ghar closes: is 31 March 2027, 230 days away. You qualify today.',
            is_a_forecast: false,
          },
        ]}
      />,
    );
    expect(screen.getByTestId('signal')).toHaveTextContent('31 March 2027');
    expect(
      screen.getByText(/Nothing here is a view on where prices are going/i),
    ).toBeInTheDocument();
  });
});

describe('unquantified benefits', () => {
  it('names a benefit that applies but is not in the figures', () => {
    render(
      <OptionComparison
        options={[option()]}
        unquantified={[
          'A state scheme: an amount this system has not verified.',
        ]}
      />,
    );
    expect(screen.getByTestId('unquantified')).toHaveTextContent(
      /has not verified/,
    );
  });

  it('shows nothing when every benefit is quantified', () => {
    render(<OptionComparison options={[option()]} />);
    expect(screen.queryByTestId('unquantified')).not.toBeInTheDocument();
  });
});

// ── restraint ───────────────────────────────────────────────────────────────

it('the component text expresses no view on whether to buy', () => {
  const { container } = render(
    <OptionComparison
      options={[option(), ev]}
      signals={[{ kind: 'policy_cliff', sentence: 'A window closes.', is_a_forecast: false }]}
    />,
  );
  const text = container.textContent!.toLowerCase();
  for (const word of [
    'recommend',
    'best buy',
    'you should',
    'great deal',
    'bargain',
    'act now',
    'hurry',
  ]) {
    expect(text).not.toContain(word);
  }
});
