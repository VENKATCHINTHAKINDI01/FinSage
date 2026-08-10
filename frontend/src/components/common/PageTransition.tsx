import React, { useEffect, useState, useRef } from 'react';

interface PageTransitionProps {
  children: React.ReactNode;
  /** Transition variant: 'warp' for dashboard, 'ocean' for auth pages, 'fade' for default */
  variant?: 'warp' | 'ocean' | 'fade';
  /** Delay before animation starts (ms) */
  delay?: number;
}

/**
 * Animated page wrapper with smooth enter/exit transitions.
 * Uses CSS animations with configurable styles per context.
 */
const PageTransition: React.FC<PageTransitionProps> = ({
  children,
  variant = 'warp',
  delay = 0
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  const animationClass = {
    warp: 'page-warp-enter',
    ocean: 'animate-gravity-up',
    fade: 'animate-fade-in'
  }[variant];

  return (
    <div
      ref={ref}
      className={`transition-wrapper ${isVisible ? animationClass : 'opacity-0'}`}
      style={{
        willChange: 'transform, opacity',
        minHeight: '100%'
      }}
    >
      {children}
    </div>
  );
};

export default PageTransition;
