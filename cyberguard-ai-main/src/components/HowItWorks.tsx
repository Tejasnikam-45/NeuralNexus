import { motion } from 'framer-motion';

const steps = [
  {
    label: 'INGEST',
    title: 'Payload Validation',
    desc: 'High-throughput ingestion of UPI/Card metadata via FastAPI gateways.',
    icon: '⟩⟩',
  },
  {
    label: 'SYNC',
    title: 'Behavioral Snapshot',
    desc: 'Sub-3ms retrieval of historical user benchmarks from internal Redis store.',
    icon: '◈',
  },
  {
    label: 'RULES',
    title: 'Expert Heuristics',
    desc: '20+ expert-tuned rules check for velocity and high-risk sequence patterns.',
    icon: '⬢',
  },
  {
    label: 'NEURAL ENSEMBLE',
    title: 'AI Inference',
    desc: 'Parallel scoring via XGBoost, Isolation Forest, and Deep Autoencoders.',
    icon: '◉',
  },
  {
    label: 'EXPLAIN',
    title: 'SHAP Reasoning',
    desc: 'Real-time feature attribution provides 100% transparency for every decision.',
    icon: '◈',
  },
];

const HowItWorks = () => {
  return (
    <section className="relative py-32 px-6">
      <div className="max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-20"
        >
          <h2 className="font-display text-4xl md:text-5xl font-bold mb-4">
            <span className="text-foreground">Processing</span>{' '}
            <span className="text-glow-blue text-primary">Pipeline</span>
          </h2>
          <p className="text-muted-foreground font-body text-lg">From raw data to decision in under 3 milliseconds.</p>
        </motion.div>

        <div className="relative">
          {/* Connecting line */}
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-primary/30 to-transparent hidden md:block" />

          <div className="space-y-16 md:space-y-0 md:grid md:grid-cols-1 md:gap-0">
            {steps.map((step, i) => (
              <motion.div
                key={step.label}
                initial={{ opacity: 0, x: i % 2 === 0 ? -40 : 40 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: i * 0.15 }}
                className={`relative md:flex items-center ${
                  i % 2 === 0 ? 'md:flex-row' : 'md:flex-row-reverse'
                } md:gap-12`}
              >
                {/* Content */}
                <div className={`md:w-5/12 ${i % 2 === 0 ? 'md:text-right' : 'md:text-left'}`}>
                  <div className="p-6 rounded-lg border border-border bg-cyber-card/60 backdrop-blur hover:border-primary/30 transition-colors group">
                    <span className="font-mono text-xs text-primary tracking-widest">{step.label}</span>
                    <h3 className="font-display text-xl font-bold mt-2 mb-2 text-foreground group-hover:text-glow-blue transition-all">
                      {step.title}
                    </h3>
                    <p className="font-body text-muted-foreground">{step.desc}</p>
                  </div>
                </div>

                {/* Center node */}
                <div className="hidden md:flex md:w-2/12 justify-center">
                  <motion.div
                    whileInView={{ scale: [0.5, 1] }}
                    viewport={{ once: true }}
                    className="w-12 h-12 rounded-full border-2 border-primary/40 bg-cyber-card flex items-center justify-center text-primary text-lg font-bold box-glow-blue"
                  >
                    {step.icon}
                  </motion.div>
                </div>

                {/* Spacer */}
                <div className="hidden md:block md:w-5/12" />
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default HowItWorks;
