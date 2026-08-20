/**
 * Replaces CosmicBackground/ParticleField's animated floating-bubble canvas
 * (mouse-repel physics, click-to-pop, per-frame redraws on every page) with
 * a static, professional backdrop: a faint technical grid plus two soft,
 * fixed gradient glows. No canvas, no animation loop, no event listeners —
 * pure CSS, matching the restrained "ledger" aesthetic the rest of the
 * product uses rather than a decorative particle system.
 */
export default function AppBackdrop() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden="true">
      {/* Faint dot grid, same pattern already used on the sidebar */}
      <div
        className="absolute inset-0 opacity-[0.4] dark:opacity-[0.05]"
        style={{
          backgroundImage: 'radial-gradient(circle at 1px 1px, currentColor 1px, transparent 0)',
          backgroundSize: '28px 28px',
          color: 'var(--color-line)',
        }}
      />
      {/* Two soft, fixed corner glows for depth — not particles */}
      <div className="absolute -top-40 -right-40 w-[520px] h-[520px] rounded-full bg-primary/[0.05] dark:bg-teal/[0.07] blur-3xl" />
      <div className="absolute -bottom-40 -left-40 w-[480px] h-[480px] rounded-full bg-teal/[0.04] dark:bg-primary/[0.08] blur-3xl" />
    </div>
  );
}
