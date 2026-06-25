import React, { useEffect, useRef } from 'react';

interface Particle {
  x: number;
  y: number;
  originX: number;
  originY: number;
  vx: number;
  vy: number;
  phase: number;
  colorIndex: number;
}

const colorPaletteDark = [
  'rgba(99, 102, 241, 0.5)',  // Indigo
  'rgba(245, 158, 11, 0.5)', // Amber
  'rgba(16, 185, 129, 0.5)', // Emerald
  'rgba(6, 182, 212, 0.5)',  // Cyan
  'rgba(244, 63, 94, 0.5)',  // Rose
];

const colorPaletteLight = [
  'rgba(79, 70, 229, 0.35)',   // Indigo Deep
  'rgba(217, 119, 6, 0.35)',   // Amber Deep
  'rgba(5, 150, 105, 0.35)',   // Emerald Deep
  'rgba(8, 145, 178, 0.35)',   // Cyan Deep
  'rgba(225, 29, 72, 0.35)',   // Rose Deep
];

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
      const spacing = 35; // Dense grid spacing
      const cols = Math.floor(width / spacing) + 2;
      const rows = Math.floor(height / spacing) + 2;

      for (let i = 0; i < cols; i++) {
        for (let j = 0; j < rows; j++) {
          const x = i * spacing;
          const y = j * spacing;
          
          // Patterned or randomized color selection
          const colorIndex = (i + j) % colorPaletteDark.length;

          particles.push({
            x,
            y,
            originX: x,
            originY: y,
            vx: 0,
            vy: 0,
            phase: Math.random() * Math.PI * 2,
            colorIndex,
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
    const spring = 0.04;
    const damping = 0.82;
    const repulsionRadius = 130;
    const repulsionStrength = 0.9;
    const connectionRadius = 50;

    const animate = () => {
      time += 0.012;
      
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const isDark = document.documentElement.classList.contains('dark');
      const activePalette = isDark ? colorPaletteDark : colorPaletteLight;

      // Update particle physics first
      particles.forEach((p) => {
        const waveY = Math.sin(p.originX * 0.006 + time + p.phase) * 6;
        const waveX = Math.cos(p.originY * 0.006 + time + p.phase) * 6;

        const targetX = p.originX + waveX;
        const targetY = p.originY + waveY;

        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < repulsionRadius) {
            const force = (repulsionRadius - dist) / repulsionRadius;
            const angle = Math.atan2(dy, dx);
            const targetVx = Math.cos(angle) * force * repulsionStrength * 8;
            const targetVy = Math.sin(angle) * force * repulsionStrength * 8;
            p.vx += targetVx;
            p.vy += targetVy;
          }
        }

        const ax = (targetX - p.x) * spring;
        const ay = (targetY - p.y) * spring;

        p.vx = (p.vx + ax) * damping;
        p.vy = (p.vy + ay) * damping;

        p.x += p.vx;
        p.y += p.vy;
      });

      // Draw connection lines between nearby particles that are near the cursor
      if (mouse.active) {
        ctx.lineWidth = 0.5;
        for (let i = 0; i < particles.length; i++) {
          const pi = particles[i];
          const dxMouse = pi.x - mouse.x;
          const dyMouse = pi.y - mouse.y;
          const distMouse = dxMouse * dxMouse + dyMouse * dyMouse;
          
          // Only process connections if the particle is near the mouse
          if (distMouse < repulsionRadius * repulsionRadius) {
            for (let j = i + 1; j < particles.length; j++) {
              const pj = particles[j];
              const dx = pi.x - pj.x;
              const dy = pi.y - pj.y;
              const dist = dx * dx + dy * dy;

              if (dist < connectionRadius * connectionRadius) {
                const distance = Math.sqrt(dist);
                const alpha = (1 - distance / connectionRadius) * 0.15;
                ctx.strokeStyle = isDark 
                  ? `rgba(255, 255, 255, ${alpha})` 
                  : `rgba(26, 84, 144, ${alpha})`;
                
                ctx.beginPath();
                ctx.moveTo(pi.x, pi.y);
                ctx.lineTo(pj.x, pj.y);
                ctx.stroke();
              }
            }
          }
        }
      }

      // Draw particles
      particles.forEach((p) => {
        let alphaMultiplier = 1;
        let size = 1.3;

        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 100) {
            // Light up and enlarge particles near cursor
            alphaMultiplier = 1.6;
            size = 2.0 - (dist / 100) * 0.7;
          }
        }

        const baseColor = activePalette[p.colorIndex];
        
        // Adjust alpha based on distance multipliers
        ctx.fillStyle = baseColor.replace(/[\d.]+\)$/, (val) => {
          const numericVal = parseFloat(val);
          return `${Math.min(0.9, numericVal * alphaMultiplier)})`;
        });

        ctx.beginPath();
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
