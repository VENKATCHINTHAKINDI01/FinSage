import { useEffect, useRef } from 'react';

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

const colorsDark = [
  'rgba(26, 84, 144, 0.15)',  // Primary Blue
  'rgba(13, 148, 136, 0.15)', // Teal
  'rgba(217, 119, 6, 0.12)',  // Saffron
  'rgba(99, 102, 241, 0.15)', // Indigo
];

const colorsLight = [
  'rgba(26, 84, 144, 0.08)',  // Primary Blue
  'rgba(13, 148, 136, 0.08)', // Teal
  'rgba(217, 119, 6, 0.06)',  // Saffron
  'rgba(99, 102, 241, 0.08)', // Indigo
];

export default function BubbleBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let bubbles: Bubble[] = [];
    let sparks: Spark[] = [];
    let mouse = { x: -1000, y: -1000, active: false };
    let time = 0;

    const init = () => {
      const width = (canvas.width = window.innerWidth);
      const height = (canvas.height = window.innerHeight);

      bubbles = [];
      sparks = [];

      // Determine bubble count based on screen size
      const count = Math.min(45, Math.max(15, Math.floor((width * height) / 45000)));

      for (let i = 0; i < count; i++) {
        bubbles.push(createBubble(true));
      }
    };

    const createBubble = (randomY = false): Bubble => {
      const width = canvas.width || window.innerWidth;
      const height = canvas.height || window.innerHeight;
      const r = Math.random() * 45 + 15; // Radius: 15px to 60px

      return {
        x: Math.random() * width,
        y: randomY ? Math.random() * height : height + r + Math.random() * 100,
        r,
        baseSpeedX: (Math.random() - 0.5) * 0.25,
        baseSpeedY: -(Math.random() * 0.8 + 0.3), // Float upwards
        vx: 0,
        vy: 0,
        swingAmount: Math.random() * 1.5 + 0.5,
        swingSpeed: Math.random() * 0.015 + 0.005,
        phase: Math.random() * Math.PI * 2,
        colorIndex: Math.floor(Math.random() * colorsDark.length),
        opacity: Math.random() * 0.2 + 0.08,
        popProgress: 0,
      };
    };

    const createSparks = (x: number, y: number, color: string) => {
      const sparkCount = Math.floor(Math.random() * 10) + 12;
      for (let i = 0; i < sparkCount; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = Math.random() * 4 + 2;
        const life = Math.random() * 30 + 20;

        sparks.push({
          x,
          y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - 1.0, // slight upward tendency
          r: Math.random() * 2 + 1,
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

      // Check if clicked any bubble
      for (let i = 0; i < bubbles.length; i++) {
        const b = bubbles[i];
        if (b.popProgress > 0) continue;

        const dx = b.x - clickX;
        const dy = b.y - clickY;
        const dist = Math.sqrt(dx * dx + dy * dy);

        // Click hit box is slightly generous for better user feedback
        if (dist < b.r + 12) {
          b.popProgress = 0.01; // Start pop transition
          
          const isDark = document.documentElement.classList.contains('dark');
          const bubbleColor = isDark ? colorsDark[b.colorIndex] : colorsLight[b.colorIndex];
          createSparks(b.x, b.y, bubbleColor);
          break; // only pop one bubble per click
        }
      }
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('click', handleWindowClick);
    document.addEventListener('mouseleave', handleMouseLeave);

    init();

    const animate = () => {
      time += 0.015;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const isDark = document.documentElement.classList.contains('dark');
      const currentPalette = isDark ? colorsDark : colorsLight;

      // Update and draw sparks
      sparks = sparks.filter((s) => {
        s.life -= 1;
        s.x += s.vx;
        s.y += s.vy;
        s.vy += 0.08; // gravity
        s.vx *= 0.96; // drag
        s.opacity = Math.max(0, s.life / s.maxLife);

        ctx.fillStyle = s.color.replace(/[\d.]+\)$/, `${s.opacity})`);
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();

        return s.life > 0;
      });

      // Update and draw bubbles
      bubbles.forEach((b, index) => {
        // If bubble is popping
        if (b.popProgress > 0) {
          b.popProgress += 0.12;
          if (b.popProgress >= 1) {
            // Re-spawn bubble at bottom
            bubbles[index] = createBubble(false);
            return;
          }

          // Draw expansion ring for popping bubble
          const popRadius = b.r * (1 + b.popProgress * 0.8);
          ctx.strokeStyle = currentPalette[b.colorIndex].replace(
            /[\d.]+\)$/,
            `${b.opacity * (1 - b.popProgress)})`
          );
          ctx.lineWidth = 2 * (1 - b.popProgress);
          ctx.beginPath();
          ctx.arc(b.x, b.y, popRadius, 0, Math.PI * 2);
          ctx.stroke();
          return;
        }

        // Float motion & sinusoidal swing
        const targetSpeedX = b.baseSpeedX + Math.sin(time * 0.8 + b.phase) * b.swingAmount * 0.2;
        b.vx += (targetSpeedX - b.vx) * 0.05;
        b.vy += (b.baseSpeedY - b.vy) * 0.05;

        // Mouse avoidance physics
        if (mouse.active) {
          const dx = b.x - mouse.x;
          const dy = b.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const repulsionRadius = 150;

          if (dist < repulsionRadius) {
            const force = (repulsionRadius - dist) / repulsionRadius;
            const angle = Math.atan2(dy, dx);
            const repelStrength = 1.2;

            b.vx += Math.cos(angle) * force * repelStrength;
            b.vy += Math.sin(angle) * force * repelStrength;
          }
        }

        // Apply friction
        b.vx *= 0.95;
        b.vy *= 0.95;

        // Apply velocities
        b.x += b.vx;
        b.y += b.vy;

        // Wrap around sides, but recreate if it floats off the top
        const width = canvas.width;
        if (b.x + b.r < -10) {
          b.x = width + b.r;
        } else if (b.x - b.r > width + 10) {
          b.x = -b.r;
        }

        if (b.y + b.r < -20) {
          // Re-spawn at bottom
          bubbles[index] = createBubble(false);
          return;
        }

        // Draw bubble
        const isHovered = mouse.active && Math.sqrt((b.x - mouse.x) ** 2 + (b.y - mouse.y) ** 2) < b.r + 12;
        const currentOpacity = isHovered ? Math.min(0.45, b.opacity * 1.8) : b.opacity;
        const baseColor = currentPalette[b.colorIndex];

        // Bubble 3D gradient fill
        const gradient = ctx.createRadialGradient(
          b.x - b.r * 0.25,
          b.y - b.r * 0.25,
          b.r * 0.1,
          b.x,
          b.y,
          b.r
        );
        
        gradient.addColorStop(0, 'rgba(255, 255, 255, 0.35)');
        gradient.addColorStop(0.3, baseColor.replace(/[\d.]+\)$/, `${currentOpacity * 0.4})`));
        gradient.addColorStop(0.9, baseColor.replace(/[\d.]+\)$/, `${currentOpacity})`));
        gradient.addColorStop(1, baseColor.replace(/[\d.]+\)$/, `${currentOpacity * 1.5})`));

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
        ctx.fill();

        // 3D Glass refraction edge stroke
        ctx.strokeStyle = isDark 
          ? `rgba(255, 255, 255, ${currentOpacity * 0.45})` 
          : `rgba(26, 84, 144, ${currentOpacity * 0.35})`;
        ctx.lineWidth = 1.0;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
        ctx.stroke();

        // Highlight glint (creates bubble look)
        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.beginPath();
        ctx.ellipse(
          b.x - b.r * 0.38,
          b.y - b.r * 0.38,
          b.r * 0.15,
          b.r * 0.08,
          -Math.PI / 4,
          0,
          Math.PI * 2
        );
        ctx.fill();
      });

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
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-0 transition-opacity duration-700"
      style={{ mixBlendMode: 'normal' }}
    />
  );
}
