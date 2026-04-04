import Navbar from '@/components/Navbar';
import HeroSection from '@/components/HeroSection';
import TrustedBy from '@/components/TrustedBy';
import WhySection from '@/components/WhySection';
import SolutionsSection from '@/components/SolutionsSection';

import HowItWorks from '@/components/HowItWorks';
import ContactSection from '@/components/ContactSection';
import TechStack from '@/components/TechStack';
import CTASection from '@/components/CTASection';
import Footer from '@/components/Footer';

const Index = () => (
  <div className="min-h-screen bg-background overflow-x-hidden">
    <Navbar />
    <HeroSection />
    <WhySection />
    <SolutionsSection />
    <HowItWorks />
    <ContactSection />
    <TechStack />
    <CTASection />
    <Footer />
  </div>
);

export default Index;
