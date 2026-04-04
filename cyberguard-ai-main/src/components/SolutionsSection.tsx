import { motion } from 'framer-motion';

const solutions = [
  {
    label: 'Payment Fraud',
    title: 'Decision-first Payment Security',
    desc: 'Automated ensemble scoring using XGBoost and Deep Autoencoders to detect cross-channel anomaly patterns in metadata before settlement.',
    stats: [
      { value: '60+', label: 'Behavioral Signals' },
      { value: '94.2%', label: 'Recall Accuracy' },
    ],
  },
  {
    label: 'Account Takeover',
    title: 'Session Chain Monitoring',
    desc: 'Detecting credential stuffing and session hijacking using 300-second sequence analysis and browser fingerprinting snapshots.',
    stats: [
      { value: '85ms', label: 'Decision Speed' },
      { value: '<2ms', label: 'Redis Latency' },
    ],
  },
  {
    label: 'Intelligence Trace',
    title: 'Transparent Risk Insights',
    desc: 'Every engine decision generates granular SHAP-based feature attribution, providing clear logic for Block, MFA, or Approve actions.',
    stats: [
      { value: '100%', label: 'Explainability' },
      { value: '20+', label: 'Expert Rules' },
    ],
  },
];

const SolutionsSection = () => (
  <section className="relative py-32 px-6 bg-cyber-surface/20">
    <div className="max-w-6xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="text-center mb-20"
      >
        <span className="font-mono text-xs text-secondary tracking-widest uppercase">Solutions</span>
        <h2 className="font-display text-4xl md:text-5xl font-bold mt-4">
          Comprehensive{' '}
          <span className="text-glow-purple text-secondary">Protection</span>
        </h2>
      </motion.div>

      <div className="space-y-8">
        {solutions.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="group grid md:grid-cols-[1fr_1fr] gap-8 p-8 rounded-xl border border-border bg-cyber-card/60 backdrop-blur hover:border-primary/20 transition-all"
          >
            <div>
              <span className="font-mono text-xs text-primary tracking-widest uppercase">{s.label}</span>
              <h3 className="font-display text-2xl font-bold mt-3 mb-4 text-foreground">{s.title}</h3>
              <p className="font-body text-muted-foreground leading-relaxed">{s.desc}</p>
            </div>
            <div className="flex items-center justify-center gap-12">
              {s.stats.map(stat => (
                <div key={stat.label} className="text-center">
                  <div className="font-display text-3xl font-bold text-primary text-glow-blue">{stat.value}</div>
                  <div className="font-mono text-xs text-muted-foreground mt-1">{stat.label}</div>
                </div>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

export default SolutionsSection;
