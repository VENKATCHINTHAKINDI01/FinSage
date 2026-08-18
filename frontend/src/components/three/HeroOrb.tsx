import React, { Suspense, lazy, useEffect, useState } from 'react';

/**
 * A single 3D accent for the landing hero — not a 3D-forward redesign.
 * Everything else on this page is 2D (Framer/CSS animation); this is the
 * one deliberate "selective 3D accent" per the agreed design direction.
 *
 * Loaded lazily and only past a capability/preference check, so a visitor
 * who cannot or should not run it never pays for it:
 *   - `prefers-reduced-motion` → skipped entirely, no static fallback mesh
 *     either (a motionless 3D object is still a WebGL context and a bundle
 *     fetch for zero benefit over the CSS gradient already behind it).
 *   - No WebGL, or context creation throws → the error boundary below
 *     falls back to rendering nothing rather than a broken canvas.
 *   - Below the `lg` breakpoint → not mounted at all (see Landing.tsx),
 *     both for layout reasons and because a device narrow enough to need
 *     that breakpoint is disproportionately likely to be GPU/battery-
 *     constrained.
 */

const Scene = lazy(() => import('./HeroOrbScene'));

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// WebGL context creation can throw synchronously on a machine with a
// disabled/blacklisted GPU, and that must not take the whole landing page
// down with it — hence a real class boundary rather than a hook-based one
// (React has no hook equivalent for catching render-phase throws).
class ErrorBoundaryToNull extends React.Component<
  { children: React.ReactNode; onError: () => void },
  { crashed: boolean }
> {
  state = { crashed: false };
  static getDerivedStateFromError() {
    return { crashed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.crashed ? null : this.props.children;
  }
}

export default function HeroOrb() {
  const [enabled, setEnabled] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    setEnabled(true);
  }, []);

  if (!enabled || failed) return null;

  return (
    <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
      <Suspense fallback={null}>
        <ErrorBoundaryToNull onError={() => setFailed(true)}>
          <Scene />
        </ErrorBoundaryToNull>
      </Suspense>
    </div>
  );
}
