import React, { useEffect, useRef, useCallback } from 'react';

interface Particle {
  x: number;
  y: number;
  baseX: number;
  baseY: number;
  vx: number;
  vy: number;
  radius: number;
  alpha: number;
  color: string;
  depth: number; // 0.3 - 1.0 for parallax
}

interface ParticleFieldProps {
  /** Number of particles */
  count?: number;
  /** Enable mouse parallax interaction */
  interactive?: boolean;
  /** Color theme */
  theme?: 'ocean' | 'cosmic' | 'aurora';
}

const THEMES = {
  ocean: ['rgba(6, 182, 212, {a})', 'rgba(14, 165, 233, {a})', 'rgba(59, 130, 246, {a})'],
  cosmic: ['rgba(139, 92, 246, {a})', 'rgba(168, 85, 247, {a})', 'rgba(6, 182, 212, {a})'],
  aurora: ['rgba(16, 185, 129, {a})', 'rgba(6, 182, 212, {a})', 'rgba(139, 92, 246, {a})'],
};

/**
 * Canvas-based particle system with mouse parallax and theme-awareness.
 * Performance-optimized with requestAnimationFrame.
 */
const ParticleField: React.FC<ParticleFieldProps> = ({
  count = 60,
  interactive = true,
  theme = 'ocean'
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const mouseRef = useRef({ x: -1000, y: -1000 });
  const animFrameRef = useRef<number>(0);

  const initParticles = useCallback((width: number, height: number) => {
    const colors = THEMES[theme];
    const particles: Particle[] = [];

    for (let i = 0; i < count; i++) {
      const depth = 0.3 + Math.random() * 0.7;
      const alpha = 0.1 + depth * 0.4;
      const colorTemplate = colors[Math.floor(Math.random() * colors.length)];
      const color = colorTemplate.replace('{a}', alpha.toFixed(2));

      const x = Math.random() * width;
      const y = Math.random() * height;

      particles.push({
        x, y,
        baseX: x,
        baseY: y,
        vx: (Math.random() - 0.5) * 0.3 * depth,
        vy: (Math.random() - 0.5) * 0.3 * depth,
        radius: 1 + Math.random() * 2 * depth,
        alpha,
        color,
        depth
      });
    }

    particlesRef.current = particles;
  }, [count, theme]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    const mouse = mouseRef.current;
    const particles = particlesRef.current;

    for (const p of particles) {
      // Drift movement
      p.baseX += p.vx;
      p.baseY += p.vy;

      // Wrap around
      if (p.baseX < -10) p.baseX = width + 10;
      if (p.baseX > width + 10) p.baseX = -10;
      if (p.baseY < -10) p.baseY = height + 10;
      if (p.baseY > height + 10) p.baseY = -10;

      // Mouse parallax
      let drawX = p.baseX;
      let drawY = p.baseY;

      if (interactive && mouse.x > 0) {
        const dx = mouse.x - p.baseX;
        const dy = mouse.y - p.baseY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const maxDist = 250;

        if (dist < maxDist) {
          const force = (1 - dist / maxDist) * 20 * p.depth;
          drawX -= (dx / dist) * force;
          drawY -= (dy / dist) * force;
        }
      }

      p.x = drawX;
      p.y = drawY;

      // Draw particle
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = p.color;
      ctx.fill();
    }

    // Draw connection lines between nearby particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 120) {
          const opacity = (1 - dist / 120) * 0.15;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(6, 182, 212, ${opacity})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }

    animFrameRef.current = requestAnimationFrame(draw);
  }, [interactive]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      initParticles(canvas.width, canvas.height);
    };

    const onMouseMove = (e: MouseEvent) => {
      mouseRef.current = { x: e.clientX, y: e.clientY };
    };

    const onMouseLeave = () => {
      mouseRef.current = { x: -1000, y: -1000 };
    };

    resize();
    window.addEventListener('resize', resize);
    if (interactive) {
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseleave', onMouseLeave);
    }

    animFrameRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseleave', onMouseLeave);
    };
  }, [initParticles, draw, interactive]);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-0"
      style={{ opacity: 0.8 }}
    />
  );
};

export default ParticleField;
