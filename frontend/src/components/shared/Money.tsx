import { AlertTriangle, ExternalLink, Info } from 'lucide-react';
import { useId, useState } from 'react';

/**
 * Every rupee figure in the product, and the provenance behind it — PLN-007.
 *
 * The invariant this component exists to enforce
 * ----------------------------------------------
 * A figure with no provenance CANNOT RENDER. Not "renders with a warning icon"
 * — it renders as an explicit red placeholder that is impossible to mistake for
 * a number. That asymmetry is deliberate: in a tax product a missing figure is
 * safe and a plausible-looking wrong one is not, so the failure mode has to be
 * loud and useless rather than quiet and usable.
 *
 * The temptation is a fallback: show the number, hide the popover. That is
 * exactly what v1 did across the board — figures with no basis, rendered
 * confidently, indistinguishable from computed ones. A component that can
 * render a bare number will eventually be used to render a bare number.
 *
 * Both numbering schemes
 * ----------------------
 * For FY 2026-27 onward the governing Act is the Income-tax Act 2025, whose
 * sections were renumbered wholesale. The popover shows both, and where the
 * 1961→2025 mapping is not yet verified it says so in the note rather than
 * asserting the new number.
 */

export interface Provenance {
  /** Rendered citation, e.g. "Income-tax Act, 2025 · s.16(ia) · FY 2026-27". */
  citation: string;
  fy: string;
  act: string;
  section: string | null;
  legacy_section: string | null;
  rule_id: string | null;
  /** ISO date the rule was last checked against a source. Mandatory. */
  verified_on: string;
  source_urls: string[];
  note?: string | null;
  is_assumption?: boolean;
}

export interface MoneyProps {
  /** Pre-formatted for Indian digit grouping by the backend. */
  display: string;
  provenance?: Provenance | null;
  label?: string;
  /** Days after which the underlying rule is treated as needing recheck. */
  freshnessWindowDays?: number;
  className?: string;
}

/**
 * A source URL comes from a rule pack, which is hand-edited YAML. `new URL()`
 * throws on anything malformed, and inside a render that takes down the whole
 * popover — so a typo in a source list would hide the provenance of a figure
 * that is otherwise perfectly sourced. Found by the first component test run;
 * `EvidencePanel` already had this guard and `Money` did not.
 */
function safeHost(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function ageInDays(iso: string): number | null {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  return Math.floor((Date.now() - then) / 86_400_000);
}

/**
 * Provenance is only usable if it carries a date AND something to click
 * through to. Either alone leaves the user unable to check the figure, which
 * is the whole purpose.
 */
function isUsable(p: Provenance | null | undefined): p is Provenance {
  if (!p) return false;
  if (!p.verified_on || ageInDays(p.verified_on) === null) return false;
  return Boolean(p.section || p.legacy_section || p.rule_id);
}

export function UnsourcedFigure({ label }: { label?: string }) {
  return (
    <span
      role="alert"
      data-testid="unsourced-figure"
      className="inline-flex items-center gap-1 rounded border border-danger/40 bg-danger/10 px-1.5 py-0.5 text-[12px] font-medium text-danger"
      title={
        `${label ? `${label}: ` : ''}this figure has no rule reference or ` +
        `verification date, so it is not shown. A number without provenance ` +
        `is not a number you should act on.`
      }
    >
      <AlertTriangle size={12} aria-hidden />
      unsourced — not shown
    </span>
  );
}

export function Money({
  display,
  provenance,
  label,
  freshnessWindowDays = 180,
  className = '',
}: MoneyProps) {
  const [open, setOpen] = useState(false);
  const popoverId = useId();

  // The load-bearing line. No fallback, deliberately.
  if (!isUsable(provenance)) return <UnsourcedFigure label={label} />;

  const age = ageInDays(provenance.verified_on) ?? 0;
  const stale = age > freshnessWindowDays;
  const bothSchemes = Boolean(provenance.section && provenance.legacy_section);

  return (
    <span className={`relative inline-flex items-center gap-1 ${className}`}>
      <span className="tabular-nums">{display}</span>

      <button
        type="button"
        aria-expanded={open}
        aria-controls={popoverId}
        aria-label={`Where ${label ?? 'this figure'} comes from`}
        onClick={() => setOpen((v) => !v)}
        className="text-ink-soft transition-colors hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        {stale ? (
          <AlertTriangle size={13} className="text-warning" aria-hidden />
        ) : (
          <Info size={13} aria-hidden />
        )}
      </button>

      {open && (
        <div
          id={popoverId}
          role="dialog"
          aria-label="Figure provenance"
          className="absolute left-0 top-full z-50 mt-1 w-80 rounded-lg border border-line bg-surface p-3 text-left shadow-lg"
        >
          {provenance.is_assumption && (
            <p className="mb-2 rounded bg-warning/10 px-2 py-1 text-[11px] font-medium text-warning">
              This is an assumption, not something you told us. Correct it if it
              is wrong.
            </p>
          )}

          <p className="text-[12px] font-medium text-ink">{provenance.citation}</p>

          {bothSchemes ? (
            <p className="mt-1 text-[11px] text-ink-soft">
              Income-tax Act 2025 s.{provenance.section} — the same provision
              you may know as s.{provenance.legacy_section} of the 1961 Act.
            </p>
          ) : (
            provenance.legacy_section && (
              <p className="mt-1 text-[11px] text-ink-soft">
                Cited under the 1961 Act numbering. The 2025 Act equivalent is
                not yet confirmed for this provision.
              </p>
            )
          )}

          {provenance.note && (
            <p className="mt-2 text-[11px] text-ink-soft">{provenance.note}</p>
          )}

          <dl className="mt-2 space-y-0.5 text-[11px] text-ink-soft">
            <div className="flex justify-between gap-2">
              <dt>Financial year</dt>
              <dd className="text-ink">{provenance.fy}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Rule last checked</dt>
              <dd className={stale ? 'font-medium text-warning' : 'text-ink'}>
                {provenance.verified_on} ({age} days ago)
              </dd>
            </div>
            {provenance.rule_id && (
              <div className="flex justify-between gap-2">
                <dt>Rule pack</dt>
                <dd className="font-mono text-[10px] text-ink">
                  {provenance.rule_id}
                </dd>
              </div>
            )}
          </dl>

          {stale && (
            <p className="mt-2 rounded bg-warning/10 px-2 py-1 text-[11px] text-warning">
              This rule has not been re-checked in {age} days. It is probably
              still correct, but confirm it against the source before you rely
              on the figure.
            </p>
          )}

          {provenance.source_urls.length > 0 && (
            <ul className="mt-2 space-y-1">
              {provenance.source_urls.map((url) => (
                <li key={url}>
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                  >
                    <ExternalLink size={10} aria-hidden />
                    {safeHost(url)}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </span>
  );
}
