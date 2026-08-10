import React, { useEffect, useRef, useCallback } from 'react';

interface DataStreamOverlayProps {
  /** Show the overlay (useful during loading states) */
  active?: boolean;
  /** Intensity: number of streams */
  intensity?: number;
}

/**
 * Animated data visualization overlay for the Dashboard.
 * Shows floating numbers, connection lines, and pulse effects
 * during loading states for a premium feel.
 */
const DataStreamOverlay: React.FC<DataStreamOverlayProps> = ({
  active = true,
  intensity = 12
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  interface Stream {
    x: number;
    y: number;
    speed: number;
    length: number;
    opacity: number;
    char: string;
    resetAt: number;
  }

  const streamsRef = useRef<Stream[]>([]);

  const CHARS = '₹%0123456789ABCDEF∑∆∏√∫';

  const initStreams = useCallback((width: number) => {
    const streams: Stream[] = [];
    for (let i = 0; i < intensity; i++) {
      streams.push({
        x: Math.random() * width,
        y: Math.random() * -500,
        speed: 0.5 + Math.random() * 1.5,
        length: 30 + Math.random() * 80,
        opacity: 0.08 + Math.random() * 0.15,
        char: CHARS[Math.floor(Math.random() * CHARS.length)],
        resetAt: -50
      });
    }
    streamsRef.current = streams;
  }, [intensity]);

  const draw = useCallback(() => {
    if (!active) {
      animFrameRef.current = requestAnimationFrame(draw);
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    for (const stream of streamsRef.current) {
      // Move stream down
      stream.y += stream.speed;

      // Reset when off screen
      if (stream.y > height + 50) {
        stream.y = -stream.length;
        stream.x = Math.random() * width;
        stream.char = CHARS[Math.floor(Math.random() * CHARS.length)];
      }

      // Draw stream line
      const gradient = ctx.createLinearGradient(stream.x, stream.y, stream.x, stream.y + stream.length);
      gradient.addColorStop(0, `rgba(6, 182, 212, 0)`);
      gradient.addColorStop(0.5, `rgba(6, 182, 212, ${stream.opacity})`);
      gradient.addColorStop(1, `rgba(6, 182, 212, 0)`);

      ctx.beginPath();
      ctx.moveTo(stream.x, stream.y);
      ctx.lineTo(stream.x, stream.y + stream.length);
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 1;
      ctx.stroke();

      // Draw character at stream head
      ctx.font = '10px JetBrains Mono, monospace';
      ctx.fillStyle = `rgba(6, 182, 212, ${stream.opacity * 2.5})`;
      ctx.fillText(stream.char, stream.x - 4, stream.y + stream.length);
    }

    animFrameRef.current = requestAnimationFrame(draw);
  }, [active]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
      initStreams(canvas.width);
    };

    resize();
    window.addEventListener('resize', resize);
    animFrameRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener('resize', resize);
    };
  }, [initStreams, draw]);

  if (!active) return null;

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none z-0"
      style={{ width: '100%', height: '100%', opacity: 0.7 }}
    />
  );
};

export default DataStreamOverlay;
