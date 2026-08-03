import Lenis from "lenis";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

let lenis: Lenis | null = null;

export function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Starts the Lenis smooth-scroll engine and syncs it with GSAP's ticker/ScrollTrigger. No-op if already running or if the user prefers reduced motion. */
export function initLenis(): Lenis | null {
  if (lenis || prefersReducedMotion()) return lenis;

  lenis = new Lenis({ duration: 1.15, smoothWheel: true });
  lenis.on("scroll", ScrollTrigger.update);

  gsap.ticker.add((time) => lenis?.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);

  return lenis;
}

export function destroyLenis(): void {
  lenis?.destroy();
  lenis = null;
}

/** Smooth-scrolls to an in-page anchor, using Lenis when available and falling back to native scrolling otherwise. */
export function scrollToHash(hash: string): void {
  if (hash.length < 2) return; // guards a bare "#" placeholder -- querySelector("#") throws

  const target = document.querySelector<HTMLElement>(hash);
  if (!target) return;

  if (lenis) {
    lenis.scrollTo(target, { offset: -70, duration: 1.2 });
  } else {
    target.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  }
}
