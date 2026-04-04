const Footer = () => (
  <footer className="border-t border-border bg-cyber-card/30 py-12 px-6">
    <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
      <div className="flex items-center gap-3 font-logo text-xl tracking-widest font-bold lowercase text-foreground">
        <img src="/logo.png" alt="Neural Watch" className="h-12 sm:h-14 w-auto dark:mix-blend-screen opacity-90 object-contain" />
        <div>
          neural<span className="text-primary ml-1">watch</span>
        </div>
      </div>
      <div className="font-mono text-xs text-muted-foreground text-center md:text-right">
        © 2026 neural watch — All systems operational
      </div>
    </div>
  </footer>
);

export default Footer;
