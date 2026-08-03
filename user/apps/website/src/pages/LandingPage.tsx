import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { scrollToHash } from "../lib/lenis";
import { Hero } from "../components/sections/Hero";
import { Marquee } from "../components/sections/Marquee";
import { Features } from "../components/sections/Features";
import { HowItWorks } from "../components/sections/HowItWorks";
import { DemoCta } from "../components/sections/DemoCta";
import { Pricing } from "../components/sections/Pricing";
import { Faq } from "../components/sections/Faq";
import { FinalCta } from "../components/sections/FinalCta";

export function LandingPage() {
  const location = useLocation();

  // Lets nav/footer links work from other pages too: they route to "/#section"
  // first, then this scrolls once the landing page has actually mounted.
  useEffect(() => {
    if (!location.hash) return;
    const id = setTimeout(() => scrollToHash(location.hash), 80);
    return () => clearTimeout(id);
  }, [location.hash]);

  return (
    <main id="top">
      <Hero />
      <Marquee />
      <Features />
      <HowItWorks />
      <DemoCta />
      <Pricing />
      <Faq />
      <FinalCta />
    </main>
  );
}
