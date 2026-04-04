import { motion } from 'framer-motion';

const logos = [
  'Mastercard', 'Citi', 'Revolut', 'Stripe', 'PayPal', 'Square', 'Klarna', 'Brex',
];

const TrustedBy = () => (
  <section className="relative border-y border-border bg-cyber-card/30 py-8 overflow-hidden">
    <div className="max-w-7xl mx-auto px-6">
      <p className="font-mono text-xs text-muted-foreground tracking-widest uppercase text-center mb-6">
        Protecting 500+ Global Brands
      </p>
      <div className="relative overflow-hidden">
        <div className="flex animate-marquee gap-16 items-center">
          {[...logos, ...logos].map((name, i) => (
            <motion.span
              key={`${name}-${i}`}
              className="font-display text-lg text-muted-foreground/40 whitespace-nowrap tracking-wider select-none"
              whileHover={{ scale: 1.05 }}
            >
              {name}
            </motion.span>
          ))}
        </div>
      </div>
    </div>
  </section>
);

export default TrustedBy;
