import { motion } from 'framer-motion';

const techs = [
  { name: 'FastAPI', icon: '⚡' },
  { name: 'Python', icon: '🐍' },
  { name: 'Redis', icon: '🚀' },
  { name: 'XGBoost', icon: '📈' },
  { name: 'PyTorch', icon: '🔥' },
  { name: 'React', icon: '⚛' },
  { name: 'Tailwind', icon: '🎨' },
  { name: 'SHAP', icon: '🔍' },
];

const TechStack = () => {
  return (
    <section className="relative py-32 px-6">
      <div className="max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="font-display text-4xl md:text-5xl font-bold mb-4">
            <span className="text-foreground">Built With</span>{' '}
            <span className="text-glow-purple text-secondary">Power</span>
          </h2>
        </motion.div>

        <div className="flex flex-wrap justify-center gap-6">
          {techs.map((tech, i) => (
            <motion.div
              key={tech.name}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              whileHover={{ scale: 1.1, y: -5 }}
              className="group relative px-6 py-4 rounded-lg border border-border bg-cyber-card/60 backdrop-blur cursor-default transition-all hover:border-primary/40 hover:box-glow-blue"
            >
              <div className="text-3xl mb-2 text-center">{tech.icon}</div>
              <div className="font-mono text-xs text-muted-foreground group-hover:text-foreground transition-colors text-center">
                {tech.name}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default TechStack;
