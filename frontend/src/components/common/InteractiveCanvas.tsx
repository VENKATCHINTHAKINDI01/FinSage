import React, { useEffect, useRef } from 'react';

interface Particle {
  x: number;
  y: number;
  originX: number;
  originY: number;
  vx: number;
  vy: number;
  phase: number;
}

export const InteractiveCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let particles: Particle[] = [];
    let mouse = { x: -1000, y: -1000, active: false };

    const init = () => {
      const width = (canvas.width = window.innerWidth);
      const height = (canvas.height = window.innerHeight);

      particles = [];
      const spacing = 40; // Spacing between dots
      const cols = Math.floor(width / spacing) + 2;
      const rows = Math.floor(height / spacing) + 2;

      for (let i = 0; i < cols; i++) {
        for (let j = 0; j < rows; j++) {
          const x = i * spacing;
          const y = j * spacing;
          particles.push({
            x,
            y,
            originX: x,
            originY: y,
            vx: 0,
            vy: 0,
            phase: Math.random() * Math.PI * 2,
          });
        }
      }
    };

    const handleResize = () => {
      init();
    };

    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      mouse.active = true;
    };

    const handleMouseLeave = () => {
      mouse.x = -1000;
      mouse.y = -1000;
      mouse.active = false;
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', handleMouseLeave);

    init();

    let time = 0;
    const spring = 0.03;
    const damping = 0.85;
    const repulsionRadius = 120;
    const repulsionStrength = 0.8;

    const animate = () => {
      time += 0.015;
      
      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Detect theme dynamically from class on <html>
      const isDark = document.documentElement.classList.contains('dark');
      ctx.fillStyle = isDark ? 'rgba(226, 232, 240, 0.22)' : 'rgba(26, 84, 144, 0.16)';

      particles.forEach((p) => {
        // Subtle ambient wave behavior using sine waves
        const waveY = Math.sin(p.originX * 0.005 + time + p.phase) * 8;
        const waveX = Math.cos(p.originY * 0.005 + time + p.phase) * 8;

        const targetX = p.originX + waveX;
        const targetY = p.originY + waveY;

        // Interaction with mouse
        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < repulsionRadius) {
            // Force calculation (stronger repulsion closer to mouse)
            const force = (repulsionRadius - dist) / repulsionRadius;
            const angle = Math.atan2(dy, dx);
            const targetVx = Math.cos(angle) * force * repulsionStrength * 10;
            const targetVy = Math.sin(angle) * force * repulsionStrength * 10;
            p.vx += targetVx;
            p.vy += targetVy;
          }
        }

        // Spring system towards target coordinate
        const ax = (targetX - p.x) * spring;
        const ay = (targetY - p.y) * spring;

        p.vx = (p.vx + ax) * damping;
        p.vy = (p.vy + ay) * damping;

        p.x += p.vx;
        p.y += p.vy;

        // Render dot
        ctx.beginPath();
        // Slightly larger dot if mouse is near
        const size = mouse.active && Math.abs(p.x - mouse.x) < 80 && Math.abs(p.y - mouse.y) < 80 ? 2 : 1.2;
        ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
        ctx.fill();
      });

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-0 transition-opacity duration-500"
      style={{ mixBlendMode: 'normal' }}
    />
  );
};

export default InteractiveCanvas;
