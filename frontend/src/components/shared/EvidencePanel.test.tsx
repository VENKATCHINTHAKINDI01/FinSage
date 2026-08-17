/**
 * EVD-005 — the evidence and working panel.
 *
 * The claims under test are the acceptance criteria, not the styling:
 * Working shows the trace rather than a summary of it, an assumption is
 * addressable and not merely visible, Confidence quantifies each remedy, and
 * the whole thing is reachable by keyboard.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EvidencePanel, type PanelPayload } from './EvidencePanel';

const TRACE_LINES = [
  'Income tax — FY 2026-27 (AY 2027-28) · New regime (default)',
  '────────────────────────────────────────',
  'Salary                                    ₹15,00,000',
  'Standard deduction (salary)                  ₹75,000',
  'Taxable income                            ₹14,25,000',
];

function payload(over: Partial<PanelPayload> = {}): PanelPayload {
  return {
    fy: '2026-27',
    tabs: {
      working: [
        {
          title: 'Income tax — FY 2026-27',
          lines: TRACE_LINES,
          result: '₹97,500',
          replays: true,
        },
      ],
      sources: [
        {
          citation: 'Income-tax Act, 2025 · s.16(ia) · FY 2026-27',
          act: 'Income-tax Act, 2025',
          section: null,
          legacy_section: '16(ia)',
          both_numbering_schemes: false,
          verified_on: '2026-08-09',
          source_urls: ['https://www.incometax.gov.in/'],
          note: null,
          decided: ['Standard deduction (salary)'],
        },
      ],
      assumptions: [],
      confidence: {
        level: 'partial',
        display: 'Partial confidence',
        summary: 'Partial confidence — mainly because rent was assumed.',
        what_would_raise_it: [
          {
            remedy: 'confirm or correct rent',
            gain: '0.10',
            because: 'rent: assumed ₹30k/mo',
            kind: 'assumption',
          },
        ],
      },
    },
    counts: { worksheets: 1, sources: 1, assumptions: 0 },
    has_unreplayable_worksheet: false,
    ...over,
  };
}

const withAssumption = () =>
  payload({
    tabs: {
      ...payload().tabs,
      assumptions: [
        {
          what: 'rent',
          value: '₹30,000 a month',
          edits_field: 'rent',
          gain_if_confirmed: '0.10',
        },
      ],
    },
    counts: { worksheets: 1, sources: 1, assumptions: 1 },
  });

describe('Working shows the trace, not a narration of it', () => {
  it('renders every line verbatim', () => {
    render(<EvidencePanel panel={payload()} />);
    const pre = screen.getByText(/Income tax — FY 2026-27 \(AY 2027-28\)/);
    for (const line of TRACE_LINES) {
      expect(pre.textContent).toContain(line);
    }
  });

  it('opens on Working by default', () => {
    render(<EvidencePanel panel={payload()} />);
    expect(screen.getByRole('tab', { name: /working/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('marks a worksheet that replays', () => {
    render(<EvidencePanel panel={payload()} />);
    expect(screen.getByLabelText('replays correctly')).toBeInTheDocument();
  });

  it('warns loudly when a worksheet does not reproduce its own result', () => {
    render(
      <EvidencePanel
        panel={payload({
          has_unreplayable_worksheet: true,
          tabs: {
            ...payload().tabs,
            working: [{ ...payload().tabs.working[0], replays: false }],
          },
        })}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/do not rely on these figures/i);
    expect(screen.getByLabelText('does not replay')).toBeInTheDocument();
  });

  it('shows no alarm on a clean panel', () => {
    render(<EvidencePanel panel={payload()} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('Sources', () => {
  it('lists the provision, what it decided and when it was checked', async () => {
    render(<EvidencePanel panel={payload()} />);
    await userEvent.click(screen.getByRole('tab', { name: /sources/i }));
    const tab = screen.getByRole('tabpanel', { name: /sources/i });
    expect(tab).toHaveTextContent('s.16(ia)');
    expect(tab).toHaveTextContent('Standard deduction (salary)');
    expect(tab).toHaveTextContent('2026-08-09');
  });

  it('explains the 1961 equivalent only where both numbers are known', async () => {
    const p = payload();
    p.tabs.sources[0] = {
      ...p.tabs.sources[0],
      section: '156',
      legacy_section: '87A',
      both_numbering_schemes: true,
    };
    render(<EvidencePanel panel={p} />);
    await userEvent.click(screen.getByRole('tab', { name: /sources/i }));
    expect(screen.getByRole('tabpanel', { name: /sources/i })).toHaveTextContent(
      /you may know as s\.87A of the 1961 Act/i,
    );
  });
});

describe('Assumptions are addressable, not merely visible', () => {
  it('says plainly that these are not facts the user gave', async () => {
    render(<EvidencePanel panel={withAssumption()} />);
    await userEvent.click(screen.getByRole('tab', { name: /assumptions/i }));
    expect(screen.getByRole('tabpanel', { name: /assumptions/i })).toHaveTextContent(
      /these are not facts you gave us/i,
    );
  });

  it('states what confirming one is worth', async () => {
    render(<EvidencePanel panel={withAssumption()} />);
    await userEvent.click(screen.getByRole('tab', { name: /assumptions/i }));
    expect(screen.getByText(/raises confidence by 0\.10/i)).toBeInTheDocument();
  });

  it('hands back the FIELD to correct, not the displayed value', async () => {
    /** Correcting an assumption must re-run the computation. A handler given a
     *  value could only patch the answer in place. */
    const onCorrect = vi.fn();
    render(<EvidencePanel panel={withAssumption()} onCorrectAssumption={onCorrect} />);
    await userEvent.click(screen.getByRole('tab', { name: /assumptions/i }));
    await userEvent.click(screen.getByRole('button', { name: /correct/i }));
    expect(onCorrect).toHaveBeenCalledWith('rent');
  });

  it('offers no correct button when no handler is wired', async () => {
    render(<EvidencePanel panel={withAssumption()} />);
    await userEvent.click(screen.getByRole('tab', { name: /assumptions/i }));
    expect(screen.queryByRole('button', { name: /correct/i })).not.toBeInTheDocument();
  });

  it('says so when nothing was assumed rather than showing an empty box', async () => {
    render(<EvidencePanel panel={payload()} />);
    await userEvent.click(screen.getByRole('tab', { name: /assumptions/i }));
    expect(screen.getByRole('tabpanel', { name: /assumptions/i })).toHaveTextContent(
      /nothing here was assumed/i,
    );
  });
});

describe('Confidence quantifies each remedy', () => {
  it('pairs the remedy with what it is worth', async () => {
    render(<EvidencePanel panel={payload()} />);
    await userEvent.click(screen.getByRole('tab', { name: /confidence/i }));
    const tab = screen.getByRole('tabpanel', { name: /confidence/i });
    expect(within(tab).getByText('+0.10')).toBeInTheDocument();
    expect(tab).toHaveTextContent('confirm or correct rent');
  });

  it('says nothing would raise a certain result', async () => {
    const p = payload();
    p.tabs.confidence = {
      level: 'certain',
      display: 'Certain',
      is_certain: true,
      what_would_raise_it: [],
    };
    render(<EvidencePanel panel={p} />);
    await userEvent.click(screen.getByRole('tab', { name: /confidence/i }));
    expect(screen.getByRole('tabpanel', { name: /confidence/i })).toHaveTextContent(
      /exact rather than estimated/i,
    );
  });
});

describe('accessibility and print', () => {
  it('wires every tab to its panel', () => {
    render(<EvidencePanel panel={payload()} />);
    for (const name of [/working/i, /sources/i, /assumptions/i, /confidence/i]) {
      const tab = screen.getByRole('tab', { name });
      expect(
        document.getElementById(tab.getAttribute('aria-controls')!),
      ).toBeInTheDocument();
    }
  });

  it('is navigable by keyboard', async () => {
    render(<EvidencePanel panel={payload()} />);
    await userEvent.tab();
    expect(screen.getByRole('tab', { name: /working/i })).toHaveFocus();
    await userEvent.tab();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByRole('tab', { name: /sources/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('keeps every tab in the DOM so a printed page carries all four', () => {
    /** `print:block` overrides `hidden`. A separate print view would be a
     *  second thing to keep correct. */
    /** Queried by id rather than accessible name: a `hidden` panel is out of
     *  the accessibility tree entirely, so it has no name to match on. */
    render(<EvidencePanel panel={payload()} />);
    for (const name of [/sources/i, /assumptions/i, /confidence/i]) {
      const id = screen
        .getByRole('tab', { name })
        .getAttribute('aria-controls')!;
      const panel = document.getElementById(id)!;
      expect(panel).toBeInTheDocument();
      expect(panel).toHaveClass('print:block');
    }
  });

  it('prints on request', async () => {
    const print = vi.fn();
    vi.stubGlobal('print', print);
    render(<EvidencePanel panel={payload()} />);
    await userEvent.click(screen.getByRole('button', { name: /print/i }));
    expect(print).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
