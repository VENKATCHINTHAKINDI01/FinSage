import { useEffect, useRef } from 'react';

interface CosmicBackgroundProps {
  mode: 'ocean' | 'space';
}

interface Bubble {
  x: number;
  y: number;
  r: number;
  baseSpeedX: number;
  baseSpeedY: number;
  vx: number;
  vy: number;
  swingAmount: number;
  swingSpeed: number;
  phase: number;
  colorIndex: number;
  opacity: number;
  popProgress: number; // 0 to 1, where >0 means popping
}

interface Star {
  x: number;
  y: number;
  r: number;
  vx: number;
  vy: number;
  opacity: number;
  baseOpacity: number;
  twinkleSpeed: number;
  phase: number;
  colorIndex: number;
}

interface Spark {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  color: string;
  opacity: number;
  life: number;
  maxLife: number;
}

const colorsOceanDark = [
  'rgba(6, 182, 212, 0.15)',  // Cyan
  'rgba(13, 148, 136, 0.15)', // Teal
  'rgba(99, 102, 241, 0.15)', // Indigo
  'rgba(26, 84, 144, 0.15)',  // Navy/Primary
];

const colorsOceanLight = [
  'rgba(6, 182, 212, 0.08)',
  'rgba(13, 148, 136, 0.08)',
  'rgba(99, 102, 241, 0.08)',
  'rgba(26, 84, 144, 0.08)',
];

const colorsSpaceDark = [
  'rgba(139, 92, 246, 0.25)', // Purple
  'rgba(99, 102, 241, 0.22)', // Indigo
  'rgba(6, 182, 212, 0.25)',  // Cyan
  'rgba(245, 158, 11, 0.18)', // Saffron
];

const colorsSpaceLight = [
  'rgba(139, 92, 246, 0.12)',
  'rgba(99, 102, 241, 0.10)',
  'rgba(6, 182, 212, 0.12)',
  'rgba(245, 158, 11, 0.08)',
];

export default function CosmicBackground({ mode }: CosmicBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let bubbles: Bubble[] = [];
    let stars: Star[] = [];
    let sparks: Spark[] = [];
    let mouse = { x: -1000, y: -1000, active: false };
    let time = 0;

    const init = () => {
      const width = (canvas.width = window.innerWidth);
      const height = (canvas.height = window.innerHeight);

      bubbles = [];
      stars = [];
      sparks = [];

      if (mode === 'ocean') {
        const count = Math.min(40, Math.max(15, Math.floor((width * height) / 45000)));
        for (let i = 0; i < count; i++) {
          bubbles.push(createBubble(true));
        }
      } else {
        const count = Math.min(90, Math.max(40, Math.floor((width * height) / 18000)));
        for (let i = 0; i < count; i++) {
          stars.push(createStar(true));
        }
      }
    };

    const createBubble = (randomY = false): Bubble => {
      const width = canvas.width || window.innerWidth;
      const height = canvas.height || window.innerHeight;
      const r = Math.random() * 40 + 15;

      return {
        x: Math.random() * width,
        y: randomY ? Math.random() * height : height + r + Math.random() * 100,
        r,
        baseSpeedX: (Math.random() - 0.5) * 0.25,
        baseSpeedY: -(Math.random() * 0.8 + 0.3),
        vx: 0,
        vy: 0,
        swingAmount: Math.random() * 1.5 + 0.5,
        swingSpeed: Math.random() * 0.015 + 0.005,
        phase: Math.random() * Math.PI * 2,
        colorIndex: Math.floor(Math.random() * colorsOceanDark.length),
        opacity: Math.random() * 0.18 + 0.08,
        popProgress: 0,
      };
    };

    const createStar = (randomize = false): Star => {
      const width = canvas.width || window.innerWidth;
      const height = canvas.height || window.innerHeight;
      const r = Math.random() * 2.2 + 0.6; // Small dust to shining star

      return {
        x: Math.random() * width,
        y: randomize ? Math.random() * height : height + r + Math.random() * 10,
        r,
        vx: (Math.random() - 0.5) * 0.08,
        vy: -(Math.random() * 0.1 + 0.05), // drift up very slowly
        opacity: Math.random() * 0.5 + 0.2,
        baseOpacity: Math.random() * 0.6 + 0.2,
        twinkleSpeed: Math.random() * 0.02 + 0.005,
        phase: Math.random() * Math.PI * 2,
        colorIndex: Math.floor(Math.random() * colorsSpaceDark.length),
      };
    };

    const createSparks = (x: number, y: number, color: string, countMultiplier = 1) => {
      const sparkCount = Math.floor((Math.random() * 8 + 10) * countMultiplier);
      for (let i = 0; i < sparkCount; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = Math.random() * 3.5 + 1.5;
        const life = Math.random() * 25 + 15;

        sparks.push({
          x,
          y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - (mode === 'ocean' ? 1.0 : 0),
          r: Math.random() * 1.8 + 0.8,
          color,
          opacity: 0.85,
          life,
          maxLife: life,
        });
      }
    };

    const handleResize = () => {
      init();
    };

    const handleMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
      mouse.active = true;
    };

    const handleMouseLeave = () => {
      mouse.x = -1000;
      mouse.y = -1000;
      mouse.active = false;
    };

    const handleWindowClick = (e: MouseEvent) => {
      const clickX = e.clientX;
      const clickY = e.clientY;
      const isDark = document.documentElement.classList.contains('dark');

      if (mode === 'ocean') {
        // Pop bubbles
        for (let i = 0; i < bubbles.length; i++) {
          const b = bubbles[i];
          if (b.popProgress > 0) continue;

          const dx = b.x - clickX;
          const dy = b.y - clickY;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < b.r + 12) {
            b.popProgress = 0.01;
            const color = isDark ? colorsOceanDark[b.colorIndex] : colorsOceanLight[b.colorIndex];
            createSparks(b.x, b.y, color);
            break;
          }
        }
      } else {
        // Space Mode: Sparkle supernova ripple on clicks
        const color = isDark ? 'rgba(139, 92, 246, 0.45)' : 'rgba(99, 102, 241, 0.35)';
        createSparks(clickX, clickY, color, 1.8);
      }
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('click', handleWindowClick);
    document.addEventListener('mouseleave', handleMouseLeave);

    init();

    const animate = () => {
      time += 0.012;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const isDark = document.documentElement.classList.contains('dark');

      // 1. Update and draw explosions/sparks
      sparks = sparks.filter((s) => {
        s.life -= 1;
        s.x += s.vx;
        s.y += s.vy;
        if (mode === 'ocean') {
          s.vy += 0.07; // ocean gravity sinks sparks
        } else {
          s.vy += 0.01; // minimal space gravity drift
        }
        s.vx *= 0.96;
        s.opacity = Math.max(0, s.life / s.maxLife);

        ctx.fillStyle = s.color.replace(/[\d.]+\)$/, `${s.opacity})`);
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();

        return s.life > 0;
      });

      // 2. Draw modes
      if (mode === 'ocean') {
        const currentPalette = isDark ? colorsOceanDark : colorsOceanLight;

        bubbles.forEach((b, index) => {
          if (b.popProgress > 0) {
            b.popProgress += 0.12;
            if (b.popProgress >= 1) {
              bubbles[index] = createBubble(false);
              return;
            }

            const popRadius = b.r * (1 + b.popProgress * 0.8);
            ctx.strokeStyle = currentPalette[b.colorIndex].replace(
              /[\d.]+\)$/,
              `${b.opacity * (1 - b.popProgress)})`
            );
            ctx.lineWidth = 1.8 * (1 - b.popProgress);
            ctx.beginPath();
            ctx.arc(b.x, b.y, popRadius, 0, Math.PI * 2);
            ctx.stroke();
            return;
          }

          // Sine drift
          const targetSpeedX = b.baseSpeedX + Math.sin(time * 0.7 + b.phase) * b.swingAmount * 0.2;
          b.vx += (targetSpeedX - b.vx) * 0.05;
          b.vy += (b.baseSpeedY - b.vy) * 0.05;

          // Mouse repel
          if (mouse.active) {
            const dx = b.x - mouse.x;
            const dy = b.y - mouse.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const repelRadius = 140;

            if (dist < repelRadius) {
              const force = (repelRadius - dist) / repelRadius;
              const angle = Math.atan2(dy, dx);
              b.vx += Math.cos(angle) * force * 1.0;
              b.vy += Math.sin(angle) * force * 1.0;
            }
          }

          b.vx *= 0.95;
          b.vy *= 0.95;
          b.x += b.vx;
          b.y += b.vy;

          const width = canvas.width;
          if (b.x + b.r < -10) b.x = width + b.r;
          else if (b.x - b.r > width + 10) b.x = -b.r;

          if (b.y + b.r < -20) {
            bubbles[index] = createBubble(false);
            return;
          }

          const isHovered = mouse.active && Math.sqrt((b.x - mouse.x) ** 2 + (b.y - mouse.y) ** 2) < b.r + 10;
          const currentOpacity = isHovered ? Math.min(0.4, b.opacity * 1.6) : b.opacity;
          const baseColor = currentPalette[b.colorIndex];

          const gradient = ctx.createRadialGradient(
            b.x - b.r * 0.25,
            b.y - b.r * 0.25,
            b.r * 0.1,
            b.x,
            b.y,
            b.r
          );
          gradient.addColorStop(0, 'rgba(255, 255, 255, 0.35)');
          gradient.addColorStop(0.3, baseColor.replace(/[\d.]+\)$/, `${currentOpacity * 0.45})`));
          gradient.addColorStop(0.9, baseColor.replace(/[\d.]+\)$/, `${currentOpacity})`));
          gradient.addColorStop(1, baseColor.replace(/[\d.]+\)$/, `${currentOpacity * 1.4})`));

          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = isDark
            ? `rgba(255, 255, 255, ${currentOpacity * 0.4})`
            : `rgba(26, 84, 144, ${currentOpacity * 0.3})`;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
          ctx.stroke();

          // Spark highlight
          ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
          ctx.beginPath();
          ctx.ellipse(b.x - b.r * 0.35, b.y - b.r * 0.35, b.r * 0.12, b.r * 0.07, -Math.PI / 4, 0, Math.PI * 2);
          ctx.fill();
        });
      } else {
        // space mode - Constellation Network
        const currentPalette = isDark ? colorsSpaceDark : colorsSpaceLight;
        const lineDistMax = 80;
        const mouseRadius = 140;

        // Dynamic star paths
        stars.forEach((s, index) => {
          // Slow orbit drift
          s.x += s.vx;
          s.y += s.vy;

          // Twinkle effect
          s.opacity = s.baseOpacity + Math.sin(time * s.twinkleSpeed * 100 + s.phase) * 0.18;
          s.opacity = Math.max(0.1, Math.min(0.85, s.opacity));

          // Mouse repel
          if (mouse.active) {
            const dx = s.x - mouse.x;
            const dy = s.y - mouse.y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < mouseRadius) {
              const force = (mouseRadius - dist) / mouseRadius;
              const angle = Math.atan2(dy, dx);
              s.x += Math.cos(angle) * force * 0.5;
              s.y += Math.sin(angle) * force * 0.5;
            }
          }

          if (s.y + s.r < -10) {
            stars[index] = createStar(false);
            return;
          }

          // Wrap borders
          const width = canvas.width;
          if (s.x < -10) s.x = width + 10;
          else if (s.x > width + 10) s.x = -10;

          // Draw star
          const color = currentPalette[s.colorIndex];
          ctx.fillStyle = color.replace(/[\d.]+\)$/, `${s.opacity})`);
          ctx.beginPath();
          ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
          ctx.fill();

          // Twinkling soft halo on hover/interaction
          if (mouse.active) {
            const dx = s.x - mouse.x;
            const dy = s.y - mouse.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 100) {
              const haloGlow = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r * 5);
              haloGlow.addColorStop(0, color.replace(/[\d.]+\)$/, `${s.opacity * 0.4})`));
              haloGlow.addColorStop(1, 'rgba(255,255,255,0)');
              ctx.fillStyle = haloGlow;
              ctx.beginPath();
              ctx.arc(s.x, s.y, s.r * 5, 0, Math.PI * 2);
              ctx.fill();
            }
          }
        });

        // Drawing constellations lines near cursor
        if (mouse.active) {
          ctx.lineWidth = 0.5;
          for (let i = 0; i < stars.length; i++) {
            const s1 = stars[i];
            const dxMouse = s1.x - mouse.x;
            const dyMouse = s1.y - mouse.y;
            const distMouse = dxMouse * dxMouse + dyMouse * dyMouse;

            if (distMouse < mouseRadius * mouseRadius) {
              for (let j = i + 1; j < stars.length; j++) {
                const s2 = stars[j];
                const dx = s1.x - s2.x;
                const dy = s1.y - s2.y;
                const dist = dx * dx + dy * dy;

                if (dist < lineDistMax * lineDistMax) {
                  const distance = Math.sqrt(dist);
                  const mouseWeight = (1 - Math.sqrt(distMouse) / mouseRadius);
                  const distanceWeight = (1 - distance / lineDistMax);
                  const alpha = mouseWeight * distanceWeight * 0.28;

                  ctx.strokeStyle = isDark
                    ? `rgba(139, 92, 246, ${alpha})`
                    : `rgba(99, 102, 241, ${alpha})`;

                  ctx.beginPath();
                  ctx.moveTo(s1.x, s1.y);
                  ctx.lineTo(s2.x, s2.y);
                  ctx.stroke();
                }
              }
            }
          }
        }
      }

      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('click', handleWindowClick);
      document.removeEventListener('mouseleave', handleMouseLeave);
      cancelAnimationFrame(animationFrameId);
    };
  }, [mode]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-0 transition-opacity duration-700"
      style={{ mixBlendMode: 'normal' }}
    />
  );
}
