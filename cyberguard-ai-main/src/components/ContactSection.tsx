import { motion } from 'framer-motion';
import { Mail, MapPin, Phone } from 'lucide-react';

const ContactSection = () => {
  return (
    <section id="contact" className="relative py-32 px-6 bg-background">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="font-display text-4xl md:text-5xl font-bold mb-6">
            Get in <span className="bg-gradient-to-r from-primary via-secondary to-neon-green bg-clip-text text-transparent">Touch</span>
          </h2>
          <p className="text-muted-foreground font-body text-lg max-w-xl mx-auto">
            Ready to integrate Neural Watch into your ecosystem? Connect with our security specialists today.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-12 max-w-5xl mx-auto">
          {/* Contact Info */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            className="flex flex-col gap-8"
          >
            <div className="flex items-start gap-4 p-6 rounded-xl border border-border bg-cyber-card/30 backdrop-blur-md">
              <div className="p-3 rounded-lg bg-primary/10 text-primary">
                <Mail className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-display font-medium text-foreground mb-1">Email Us</h3>
                <p className="text-muted-foreground font-mono text-sm leading-relaxed">
                  operations@neuralwatch.ai<br />
                  support@neuralwatch.ai
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-6 rounded-xl border border-border bg-cyber-card/30 backdrop-blur-md">
              <div className="p-3 rounded-lg bg-secondary/10 text-secondary">
                <Phone className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-display font-medium text-foreground mb-1">Call Us</h3>
                <p className="text-muted-foreground font-mono text-sm leading-relaxed">
                  +91 7620044488<br />
                  Mon-Fri, 9am - 6pm IST
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-6 rounded-xl border border-border bg-cyber-card/30 backdrop-blur-md">
              <div className="p-3 rounded-lg bg-neon-green/10 text-neon-green">
                <MapPin className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-display font-medium text-foreground mb-1">Headquarters</h3>
                <p className="text-muted-foreground font-mono text-sm leading-relaxed">
                  Neural Watch ACPCE<br />
                  KHARGHAR, Navi Mumbai<br />
                  Maharashtra 410210
                </p>
              </div>
            </div>
          </motion.div>

          {/* Form */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
          >
            <form className="flex flex-col gap-5 p-8 rounded-xl border border-border bg-cyber-card/30 backdrop-blur-md" onSubmit={(e) => e.preventDefault()}>
              <div>
                <label className="block text-xs font-mono text-muted-foreground mb-2 uppercase tracking-wider">Full Name</label>
                <input
                  type="text"
                  placeholder="John Doe"
                  className="w-full bg-background border border-border rounded-lg px-4 py-3 text-foreground font-mono text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                />
              </div>
              
              <div>
                <label className="block text-xs font-mono text-muted-foreground mb-2 uppercase tracking-wider">Work Email</label>
                <input
                  type="email"
                  placeholder="john@company.com"
                  className="w-full bg-background border border-border rounded-lg px-4 py-3 text-foreground font-mono text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all"
                />
              </div>

              <div>
                <label className="block text-xs font-mono text-muted-foreground mb-2 uppercase tracking-wider">Inquiry Type</label>
                <select className="w-full bg-background border border-border rounded-lg px-4 py-3 text-foreground font-mono text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all appearance-none cursor-pointer">
                  <option value="demo">Request a Demo</option>
                  <option value="sales">Sales Inquiry</option>
                  <option value="support">Technical Support</option>
                  <option value="partnership">Partnership</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-mono text-muted-foreground mb-2 uppercase tracking-wider">Message</label>
                <textarea
                  rows={4}
                  placeholder="How can we help secure your systems?"
                  className="w-full bg-background border border-border rounded-lg px-4 py-3 text-foreground font-mono text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-all resize-none"
                ></textarea>
              </div>

              <button
                type="submit"
                className="mt-2 w-full py-4 rounded-lg font-display text-sm tracking-widest uppercase text-primary-foreground transition-all hover:opacity-90 hover:scale-[1.02]"
                style={{ backgroundColor: 'hsl(350, 85%, 58%)' }}
              >
                Send Message
              </button>
            </form>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default ContactSection;
