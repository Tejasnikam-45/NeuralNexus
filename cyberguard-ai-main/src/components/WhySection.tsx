import { motion } from 'framer-motion';

const features = [
  {
    icon: '◈',
    title: 'Customizable & Scalable',
    desc: 'No-code rules engine, flexible dashboards, and tailor-made ML models that adapt and scale with your business.',
  },
  {
    icon: '⬡',
    title: 'End-to-End Platform',
    desc: 'Unify fraud detection, compliance, and risk management into one powerful solution.',
  },
  {
    icon: '◉',
    title: 'AI Precision You Can Rely On',
    desc: 'Reduce false positives with highly accurate, real-time risk scoring and anomaly detection.',
  },
];

const WhySection = () => (
  <section className="relative pt-12 pb-24 px-6">
    <div className="max-w-6xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="text-center mb-20"
      >

        <h2 className="font-display text-4xl md:text-5xl font-bold mt-4 mb-4">
          Future-Proof Your
          <br />
          <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
            Fraud & Risk Program
          </span>
        </h2>
        <p className="text-muted-foreground font-body text-lg max-w-2xl mx-auto">
          An integrated platform designed for precision, agility, and impactful results.
        </p>
      </motion.div>

      <div className="grid md:grid-cols-3 gap-8">
        {features.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.12 }}
            whileHover={{ y: -6, transition: { duration: 0.2 } }}
            className="group p-8 rounded-xl border border-border bg-cyber-card/60 backdrop-blur hover:border-primary/30 transition-all"
          >
            <div className="w-12 h-12 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary text-xl mb-6 group-hover:box-glow-blue transition-shadow">
              {f.icon}
            </div>
            <h3 className="font-display text-lg font-bold mb-3 text-foreground">{f.title}</h3>
            <p className="font-body text-muted-foreground leading-relaxed">{f.desc}</p>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

export default WhySection;
