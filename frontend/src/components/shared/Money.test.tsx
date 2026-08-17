/**
 * PLN-007 — the citation ledger UI.
 *
 * One invariant carries this component: a figure with no usable provenance
 * CANNOT RENDER. Everything else is presentation. The tests are written so that
 * removing the guard fails loudly rather than silently showing a bare number.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Money, type Provenance } from './Money';

const daysAgo = (n: number) =>
  new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

const good: Provenance = {
  citation: 'Income-tax Act, 2025 · s.16(ia) · FY 2026-27',
  fy: '2026-27',
  act: 'Income-tax Act, 2025',
  section: null,
  legacy_section: '16(ia)',
  rule_id: 'fy_2026_27',
  verified_on: daysAgo(10),
  source_urls: ['https://www.incometax.gov.in/'],
};

describe('a figure without provenance cannot render', () => {
  it('shows an explicit placeholder instead of the number', () => {
    render(<Money display="₹75,000" label="Standard deduction" />);
    expect(screen.getByTestId('unsourced-figure')).toBeInTheDocument();
    expect(screen.queryByText('₹75,000')).not.toBeInTheDocument();
  });

  it('refuses when provenance is present but undated', () => {
    render(<Money display="₹75,000" provenance={{ ...good, verified_on: '' }} />);
    expect(screen.getByTestId('unsourced-figure')).toBeInTheDocument();
  });

  it('refuses when the date is unparseable', () => {
    render(
      <Money display="₹75,000" provenance={{ ...good, verified_on: 'soon' }} />,
    );
    expect(screen.getByTestId('unsourced-figure')).toBeInTheDocument();
  });

  it('refuses when there is nothing to click through to', () => {
    render(
      <Money
        display="₹75,000"
        provenance={{ ...good, section: null, legacy_section: null, rule_id: null }}
      />,
    );
    expect(screen.getByTestId('unsourced-figure')).toBeInTheDocument();
  });

  it('announces the refusal to assistive technology', () => {
    render(<Money display="₹75,000" label="Cess" />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});

describe('a sourced figure', () => {
  it('renders the amount', () => {
    render(<Money display="₹75,000" provenance={good} />);
    expect(screen.getByText('₹75,000')).toBeInTheDocument();
  });

  it('hides the provenance until asked for', () => {
    render(<Money display="₹75,000" provenance={good} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens a popover carrying the citation, date and source', async () => {
    render(<Money display="₹75,000" provenance={good} label="Standard deduction" />);
    await userEvent.click(
      screen.getByRole('button', { name: /where standard deduction comes from/i }),
    );
    const popover = screen.getByRole('dialog');
    expect(popover).toHaveTextContent('s.16(ia)');
    expect(popover).toHaveTextContent(good.verified_on);
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      'https://www.incometax.gov.in/',
    );
  });

  it('opens and closes on repeated clicks', async () => {
    render(<Money display="₹75,000" provenance={good} />);
    const trigger = screen.getByRole('button');
    await userEvent.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await userEvent.click(trigger);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('both numbering schemes', () => {
  it('explains the 1961 equivalent when both are known', async () => {
    render(
      <Money
        display="₹60,000"
        provenance={{ ...good, section: '156', legacy_section: '87A' }}
      />,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).toHaveTextContent(
      /s\.156 — the same provision you may know as s\.87A of the 1961 Act/i,
    );
  });

  it('says the 2025 number is unconfirmed rather than inventing one', async () => {
    render(<Money display="₹60,000" provenance={good} />);
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).toHaveTextContent(/not yet confirmed/i);
  });
});

describe('staleness', () => {
  it('warns when the rule has not been re-checked inside the window', async () => {
    render(
      <Money display="₹75,000" provenance={{ ...good, verified_on: daysAgo(400) }} />,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).toHaveTextContent(
      /has not been re-checked in 400 days/i,
    );
  });

  it('does not warn inside the window', async () => {
    render(<Money display="₹75,000" provenance={good} />);
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).not.toHaveTextContent(/not been re-checked/i);
  });

  it('respects a caller-supplied window', async () => {
    render(
      <Money
        display="₹75,000"
        provenance={{ ...good, verified_on: daysAgo(20) }}
        freshnessWindowDays={7}
      />,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).toHaveTextContent(/not been re-checked/i);
  });
});

describe('assumptions', () => {
  it('are labelled as assumptions, not facts', async () => {
    render(
      <Money display="₹3,60,000" provenance={{ ...good, is_assumption: true }} />,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).toHaveTextContent(
      /this is an assumption, not something you told us/i,
    );
  });

  it('a stated figure carries no such label', async () => {
    render(<Money display="₹3,60,000" provenance={good} />);
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).not.toHaveTextContent(/is an assumption/i);
  });
});

describe('accessibility', () => {
  it('wires aria-expanded and aria-controls to the popover', async () => {
    render(<Money display="₹75,000" provenance={good} />);
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('dialog')).toHaveAttribute(
      'id',
      trigger.getAttribute('aria-controls'),
    );
  });

  it('is reachable and operable by keyboard alone', async () => {
    render(<Money display="₹75,000" provenance={good} />);
    await userEvent.tab();
    expect(screen.getByRole('button')).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('survives a malformed source url without crashing', async () => {
    render(
      <Money display="₹75,000" provenance={{ ...good, source_urls: ['not a url'] }} />,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
