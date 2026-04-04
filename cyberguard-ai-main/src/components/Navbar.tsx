import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTheme } from "next-themes";
import { ThemeToggle } from './ThemeToggle';

const navLinks = [
  { label: 'Dashboard', href: 'http://localhost:5173/', external: true },
  { label: 'Model Performance', href: 'http://localhost:5173/?tab=performance', external: true },
  { label: 'System Architecture', href: 'http://localhost:5173/?tab=architecture', external: true },
];

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const { theme, resolvedTheme } = useTheme();

  useEffect(() => {
    setMounted(true);
    const onScroll = () => setScrolled(window.scrollY > 40);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const isDark = mounted && (theme === 'dark' || resolvedTheme === 'dark');

  return (
    <motion.nav
      initial={{ y: -80 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled
        ? 'bg-background/80 backdrop-blur-xl border-b border-border shadow-sm'
        : 'bg-transparent'
        }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
        {/* Logo */}
        <a href="#" className="flex items-center gap-3 group">
          <img
            src="/logo.png"
            alt="Neural Watch"
            className={`h-12 sm:h-14 w-auto object-contain transition-all duration-300 ${isDark ? 'dark:mix-blend-screen' : 'mix-blend-multiply opacity-90'}`}
          />
          <div className="hidden sm:block leading-none">
            <div className={`font-black text-[22px] tracking-tighter leading-none bg-clip-text text-transparent transition-all duration-300 ${isDark
                ? 'bg-gradient-to-b from-white to-slate-400'
                : 'bg-gradient-to-b from-slate-900 to-slate-600'
              }`}>
              Neural Watch
            </div>
            <div className={`text-[9px] font-extrabold uppercase tracking-[0.2em] mt-1 transition-colors duration-300 ${isDark
                ? 'text-indigo-400/90'
                : 'text-indigo-600'
              }`}>
              Fraud Intelligence
            </div>
          </div>
        </a>

        {/* Desktop links */}
        <div className="hidden lg:flex items-center gap-4 xl:gap-6 lg:ml-auto lg:mr-8 xl:mr-10">
          {navLinks.map(link => (
            <a
              key={link.label}
              href={link.href}
              target={link.external ? "_blank" : "_self"}
              rel="noopener noreferrer"
              className="font-body text-base xl:text-lg font-medium text-foreground dark:text-white hover:text-primary transition-colors whitespace-nowrap"
              onClick={link.external ? undefined : (e) => { e.preventDefault(); document.getElementById(link.href.slice(1))?.scrollIntoView({ behavior: 'smooth' }) }}
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* CTA */}
        <div className="hidden md:flex items-center gap-4">
          <ThemeToggle />
          <a
            href="http://localhost:5173"
            target="_blank"
            rel="noopener noreferrer"
            className="px-8 py-3 rounded-lg font-display text-sm tracking-widest uppercase text-primary-foreground hover:opacity-90 transition-opacity"
            style={{ backgroundColor: 'hsl(350, 85%, 58%)', textDecoration: 'none' }}
          >
            Demo
          </a>
        </div>

        {/* Mobile toggle */}
        <div className="flex md:hidden items-center gap-4">
          <ThemeToggle />
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="flex flex-col gap-1.5 p-2"
          >
            <span className={`w-6 h-0.5 bg-foreground transition-transform ${mobileOpen ? 'rotate-45 translate-y-2' : ''}`} />
            <span className={`w-6 h-0.5 bg-foreground transition-opacity ${mobileOpen ? 'opacity-0' : ''}`} />
            <span className={`w-6 h-0.5 bg-foreground transition-transform ${mobileOpen ? '-rotate-45 -translate-y-2' : ''}`} />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden bg-background/95 backdrop-blur-xl border-b border-border overflow-hidden"
          >
            <div className="px-6 py-4 space-y-3">
              {navLinks.map(link => (
                <a
                  key={link.label}
                  href={link.href}
                  target={link.external ? "_blank" : "_self"}
                  className="block font-body text-sm text-muted-foreground hover:text-foreground"
                  onClick={link.external ? undefined : (e) => { e.preventDefault(); setMobileOpen(false); document.getElementById(link.href.slice(1))?.scrollIntoView({ behavior: 'smooth' }) }}
                >
                  {link.label}
                </a>
              ))}
              <a
                href="http://localhost:5173"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-2 px-5 py-2 rounded-lg font-display text-xs tracking-widest uppercase text-primary-foreground"
                style={{ backgroundColor: 'hsl(350, 85%, 58%)', textDecoration: 'none' }}
              >
                Request Demo
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
};

export default Navbar;
