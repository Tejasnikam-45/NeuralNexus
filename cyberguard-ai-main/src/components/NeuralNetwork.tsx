import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

const NeuralNetwork = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    const nodes: { x: number; y: number; vx: number; vy: number; r: number; pulse: number }[] = [];
    const nodeCount = 60;

    const resize = () => {
      canvas.width = canvas.offsetWidth * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };

    resize();

    for (let i = 0; i < nodeCount; i++) {
      nodes.push({
        x: Math.random() * canvas.offsetWidth,
        y: Math.random() * canvas.offsetHeight,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        r: 2 + Math.random() * 3,
        pulse: Math.random() * Math.PI * 2,
      });
    }

    const w = () => canvas.offsetWidth;
    const h = () => canvas.offsetHeight;

    const draw = () => {
      ctx.clearRect(0, 0, w(), h());

      // Update
      nodes.forEach(n => {
        n.x += n.vx;
        n.y += n.vy;
        n.pulse += 0.02;
        if (n.x < 0 || n.x > w()) n.vx *= -1;
        if (n.y < 0 || n.y > h()) n.vy *= -1;
      });

      // Connections
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 150) {
            const alpha = (1 - dist / 150) * 0.3;
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(56, 139, 255, ${alpha})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }

      // Nodes
      nodes.forEach(n => {
        const glow = (Math.sin(n.pulse) + 1) / 2;
        const r = n.r + glow * 2;

        // Outer glow
        const grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 4);
        grad.addColorStop(0, `rgba(56, 139, 255, ${0.15 * glow})`);
        grad.addColorStop(1, 'rgba(56, 139, 255, 0)');
        ctx.beginPath();
        ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        // Core
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(56, 139, 255, ${0.5 + glow * 0.5})`;
        ctx.fill();
      });

      animId = requestAnimationFrame(draw);
    };

    draw();
    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <section className="relative py-32 px-6 overflow-hidden">
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full"
      />
      <div className="absolute inset-0 bg-gradient-to-b from-background via-transparent to-background" />

      <div className="relative z-10 max-w-4xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <h2 className="font-display text-4xl md:text-5xl font-bold mb-6">
            <span className="text-glow-purple text-secondary">Neural</span>{' '}
            <span className="text-foreground">Architecture</span>
          </h2>
          <p className="text-muted-foreground font-body text-lg max-w-2xl mx-auto mb-8">
            A multi-layered deep learning model with 847M parameters, trained on 12B+ labeled transactions.
            Real-time inference at sub-millisecond latency.
          </p>

          <div className="grid grid-cols-3 gap-6 max-w-lg mx-auto">
            {[
              { value: '847M', label: 'Parameters' },
              { value: '0.3ms', label: 'Latency' },
              { value: '99.7%', label: 'Accuracy' },
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.2 + i * 0.1 }}
                className="p-4 rounded-lg border border-border bg-cyber-card/60 backdrop-blur"
              >
                <div className="font-display text-2xl font-bold text-primary text-glow-blue">{stat.value}</div>
                <div className="font-mono text-xs text-muted-foreground mt-1">{stat.label}</div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default NeuralNetwork;
