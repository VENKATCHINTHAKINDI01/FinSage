import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Pencil,
  Printer,
} from 'lucide-react';
import { useId, useState } from 'react';

/**
 * The evidence drawer — EVD-005.
 *
 * Four tabs, all rendered from the backend `EvidencePanel` payload. This
 * component does layout and nothing else: it never re-derives a total, never
 * rounds a figure for display, never summarises a step. Every one of those is a
 * way for the panel to disagree with the arithmetic it is supposed to be
 * evidence of.
 *
 * Working is a rendering, not a narration
 * ---------------------------------------
 * The Working tab prints `Trace.render()` verbatim — the same lines the Evidence
 * Pack contains and the same lines `replay()` verifies. If a worksheet does not
 * replay, the tab says so loudly rather than showing it as though it did.
 *
 * Printable
 * ---------
 * Tax evidence gets printed and handed to people. The panel opens all tabs for
 * print via `print:block` rather than shipping a separate print view that can
 * drift from the screen one.
 */

export interface PanelPayload {
  fy: string;
  tabs: {
    working: {
      title: string;
      lines: string[];
      result: string;
      replays: boolean;
    }[];
    sources: {
      citation: string;
      act: string;
      section: string | null;
      legacy_section: string | null;
      both_numbering_schemes: boolean;
      verified_on: string;
      source_urls: string[];
      note: string | null;
      decided: string[];
    }[];
    assumptions: {
      what: string;
      value: string;
      edits_field: string;
      gain_if_confirmed: string;
    }[];
    confidence: {
      level: string;
      display?: string;
      summary?: string;
      is_certain?: boolean;
      what_would_raise_it?: {
        remedy: string;
        gain: string;
        because: string;
        kind: string;
      }[];
    };
  };
  counts: { worksheets: number; sources: number; assumptions: number };
  has_unreplayable_worksheet: boolean;
}

type TabKey = 'working' | 'sources' | 'assumptions' | 'confidence';

const TAB_LABELS: Record<TabKey, string> = {
  working: 'Working',
  sources: 'Sources',
  assumptions: 'Assumptions',
  confidence: 'Confidence',
};

export function EvidencePanel({
  panel,
  onCorrectAssumption,
}: {
  panel: PanelPayload;
  /** Called with the profile field to correct. Correcting an assumption must
   *  re-run the computation, never patch the displayed answer. */
  onCorrectAssumption?: (field: string) => void;
}) {
  const [tab, setTab] = useState<TabKey>('working');
  const baseId = useId();

  const counts: Record<TabKey, number | null> = {
    working: panel.counts.worksheets,
    sources: panel.counts.sources,
    assumptions: panel.counts.assumptions,
    confidence: null,
  };

  return (
    <section
      aria-label="Evidence and working"
      className="rounded-lg border border-line bg-surface"
    >
      <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div
          role="tablist"
          aria-label="Evidence tabs"
          className="flex gap-1 print:hidden"
        >
          {(Object.keys(TAB_LABELS) as TabKey[]).map((key) => (
            <button
              key={key}
              id={`${baseId}-tab-${key}`}
              role="tab"
              type="button"
              aria-selected={tab === key}
              aria-controls={`${baseId}-panel-${key}`}
              onClick={() => setTab(key)}
              className={`rounded px-2.5 py-1 text-[12px] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${
                tab === key
                  ? 'bg-primary/10 font-medium text-primary'
                  : 'text-ink-soft hover:text-ink'
              }`}
            >
              {TAB_LABELS[key]}
              {counts[key] !== null && counts[key]! > 0 && (
                <span className="ml-1 text-[10px] text-ink-soft">
                  {counts[key]}
                </span>
              )}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => window.print()}
          aria-label="Print the full evidence"
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-ink-soft hover:text-primary print:hidden"
        >
          <Printer size={12} aria-hidden />
          Print
        </button>
      </header>

      {panel.has_unreplayable_worksheet && (
        <p
          role="alert"
          className="m-3 rounded border border-danger/40 bg-danger/10 px-2 py-1.5 text-[12px] text-danger"
        >
          One of these worksheets does not reproduce its own result. Do not rely
          on these figures — this is a bug, and it has been recorded.
        </p>
      )}

      {/* Every tab is rendered for print, so the printed page carries the whole
          evidence rather than whichever tab happened to be open. */}
      <div className="p-3">
        <Tab id={baseId} k="working" active={tab}>
          {panel.tabs.working.map((w) => (
            <div key={w.title} className="mb-4">
              <h4 className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-ink">
                {w.title}
                {w.replays ? (
                  <CheckCircle2
                    size={12}
                    className="text-success"
                    aria-label="replays correctly"
                  />
                ) : (
                  <AlertTriangle
                    size={12}
                    className="text-danger"
                    aria-label="does not replay"
                  />
                )}
              </h4>
              <pre className="overflow-x-auto whitespace-pre rounded bg-canvas p-2 font-mono text-[10.5px] leading-[1.45] text-ink">
                {w.lines.join('\n')}
              </pre>
            </div>
          ))}
        </Tab>

        <Tab id={baseId} k="sources" active={tab}>
          <ul className="space-y-2.5">
            {panel.tabs.sources.map((s) => (
              <li key={s.citation} className="border-l-2 border-line pl-2.5">
                <p className="text-[12px] font-medium text-ink">{s.citation}</p>
                {s.both_numbering_schemes && (
                  <p className="text-[11px] text-ink-soft">
                    Income-tax Act 2025 s.{s.section} — the provision you may
                    know as s.{s.legacy_section} of the 1961 Act.
                  </p>
                )}
                {s.note && (
                  <p className="mt-0.5 text-[11px] text-ink-soft">{s.note}</p>
                )}
                <p className="mt-0.5 text-[11px] text-ink-soft">
                  Last checked {s.verified_on} · decided{' '}
                  {s.decided.length === 1
                    ? s.decided[0]
                    : `${s.decided.length} figures`}
                </p>
                {s.source_urls.map((url) => (
                  <a
                    key={url}
                    href={url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                  >
                    <ExternalLink size={10} aria-hidden />
                    {safeHost(url)}
                  </a>
                ))}
              </li>
            ))}
          </ul>
        </Tab>

        <Tab id={baseId} k="assumptions" active={tab}>
          {panel.tabs.assumptions.length === 0 ? (
            <p className="text-[12px] text-ink-soft">
              Nothing here was assumed. Every figure came from something you
              supplied.
            </p>
          ) : (
            <>
              <p className="mb-2 text-[11px] text-ink-soft">
                These are not facts you gave us. If any is wrong, correct it —
                the figures are recomputed from scratch rather than adjusted.
              </p>
              <ul className="space-y-1.5">
                {panel.tabs.assumptions.map((a) => (
                  <li
                    key={a.edits_field}
                    className="flex items-start justify-between gap-2 rounded bg-warning/5 px-2 py-1.5"
                  >
                    <div>
                      <p className="text-[12px] text-ink">
                        <span className="font-medium">{a.what}</span>: {a.value}
                      </p>
                      <p className="text-[11px] text-warning">
                        Assumed — confirming this raises confidence by{' '}
                        {a.gain_if_confirmed}
                      </p>
                    </div>
                    {onCorrectAssumption && (
                      <button
                        type="button"
                        onClick={() => onCorrectAssumption(a.edits_field)}
                        className="inline-flex shrink-0 items-center gap-1 rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-soft hover:text-primary print:hidden"
                      >
                        <Pencil size={10} aria-hidden />
                        Correct
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Tab>

        <Tab id={baseId} k="confidence" active={tab}>
          <p className="text-[13px] font-medium text-ink">
            {panel.tabs.confidence.display ?? panel.tabs.confidence.level}
          </p>
          {panel.tabs.confidence.summary && (
            <p className="mt-0.5 text-[12px] text-ink-soft">
              {panel.tabs.confidence.summary}
            </p>
          )}

          {(panel.tabs.confidence.what_would_raise_it ?? []).length > 0 ? (
            <>
              <h4 className="mt-3 text-[12px] font-medium text-ink">
                What would raise this
              </h4>
              <ul className="mt-1 space-y-1">
                {panel.tabs.confidence.what_would_raise_it!.map((i) => (
                  <li key={i.remedy} className="text-[12px] text-ink">
                    <span className="mr-1.5 font-mono text-[11px] text-success">
                      +{i.gain}
                    </span>
                    {i.remedy}
                    <span className="ml-1 text-[11px] text-ink-soft">
                      — {i.because}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            panel.tabs.confidence.is_certain && (
              <p className="mt-2 text-[12px] text-success">
                Nothing would raise this. The inputs are complete and the rules
                are current, so the figure is exact rather than estimated.
              </p>
            )
          )}
        </Tab>
      </div>
    </section>
  );
}

function Tab({
  id,
  k,
  active,
  children,
}: {
  id: string;
  k: TabKey;
  active: TabKey;
  children: React.ReactNode;
}) {
  return (
    <div
      id={`${id}-panel-${k}`}
      role="tabpanel"
      aria-labelledby={`${id}-tab-${k}`}
      hidden={active !== k}
      // `print:block` overrides `hidden` so a printed page carries all four
      // tabs. A separate print view would be a second thing to keep correct.
      className={active === k ? 'block' : 'hidden print:block'}
    >
      {active !== k && (
        <h3 className="mb-1 mt-3 hidden text-[12px] font-semibold text-ink print:block">
          {TAB_LABELS[k]}
        </h3>
      )}
      {children}
    </div>
  );
}

function safeHost(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}
