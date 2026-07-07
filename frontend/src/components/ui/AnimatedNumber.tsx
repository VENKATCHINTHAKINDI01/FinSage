import { useEffect, useRef, useState } from 'react';

interface AnimatedNumberProps {
  value: number;
  duration?: number;         // ms
  formatter?: (v: number) => string;
  className?: string;
}

/**
 * Smoothly counts up from 0 to `value` when it first enters the viewport.
 * Works with any formatter (INR, %, plain numbers).
 */
export default function AnimatedNumber({
  value,
  duration = 900,
  formatter = (v) => v.toLocaleString('en-IN'),
  className,
}: AnimatedNumberProps) {
  const [displayed, setDisplayed] = useState(0);
  const [started, setStarted] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting && !started) setStarted(true); },
      { threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [started]);

  useEffect(() => {
    if (!started) return;
    const start = performance.now();
    let raf: number;

    function tick(now: number) {
      const progress = Math.min((now - start) / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayed(Math.round(eased * value));
      if (progress < 1) raf = requestAnimationFrame(tick);
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [started, value, duration]);

  return (
    <span ref={ref} className={className} style={{ animation: 'count-up 0.4s ease-out' }}>
      {formatter(displayed)}
    </span>
  );
}
