import { useEffect, useRef } from 'react';

const DataStreamBackground = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;
    const chars = '01アイウエオカキクケコサシスセソタチツテト■□▪▫●○◆◇';
    const columns: number[] = [];
    const drops: number[] = [];
    let fontSize = 14;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      const cols = Math.floor(canvas.width / fontSize);
      columns.length = 0;
      drops.length = 0;
      for (let i = 0; i < cols; i++) {
        columns.push(i);
        drops.push(Math.random() * -100);
      }
    };

    resize();
    window.addEventListener('resize', resize);

    const draw = () => {
      ctx.fillStyle = 'rgba(8, 10, 20, 0.06)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      for (let i = 0; i < drops.length; i++) {
        const char = chars[Math.floor(Math.random() * chars.length)];
        const x = i * fontSize;
        const y = drops[i] * fontSize;

        // Alternate between blue and purple
        if (i % 3 === 0) {
          ctx.fillStyle = 'rgba(56, 139, 255, 0.35)';
        } else if (i % 3 === 1) {
          ctx.fillStyle = 'rgba(155, 89, 255, 0.25)';
        } else {
          ctx.fillStyle = 'rgba(56, 139, 255, 0.15)';
        }

        ctx.font = `${fontSize}px "JetBrains Mono", monospace`;
        ctx.fillText(char, x, y);

        if (y > canvas.height && Math.random() > 0.985) {
          drops[i] = 0;
        }
        drops[i] += 0.5;
      }
      animationId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none"
      style={{ opacity: 0.6 }}
    />
  );
};

export default DataStreamBackground;
