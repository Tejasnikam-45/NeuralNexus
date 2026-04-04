import { motion } from 'framer-motion';

const CTASection = () => (
  <section className="relative py-32 px-6">
    <div className="max-w-4xl mx-auto text-center">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <h2 className="font-display text-4xl md:text-5xl font-bold mb-6">
          Ready to{' '}
          <span className="bg-gradient-to-r from-primary via-secondary to-neon-green bg-clip-text text-transparent">
            Secure Your Revenue
          </span>?
        </h2>
        <p className="text-muted-foreground font-body text-lg max-w-xl mx-auto mb-10">
          Join 500+ companies using Neural Watch to protect transactions, reduce false positives, and grow with confidence.
        </p>
        <div className="flex flex-wrap justify-center gap-4">
          <a
            href="http://localhost:5173"
            target="_blank"
            rel="noopener noreferrer"
            className="px-10 py-4 rounded-lg font-display text-sm tracking-widest uppercase text-primary-foreground transition-all hover:opacity-90 hover:scale-[1.02] inline-block"
            style={{ backgroundColor: 'hsl(350, 85%, 58%)', textDecoration: 'none' }}
          >
            Request a Demo
          </a>
          <button className="px-10 py-4 rounded-lg font-display text-sm tracking-widest uppercase border border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground/50 transition-all">
            Talk to Sales
          </button>
        </div>
      </motion.div>
    </div>
  </section>
);

export default CTASection;
