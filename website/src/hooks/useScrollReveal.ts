import { useEffect, useRef } from "react";
import { gsap } from "gsap";
// Registering the ScrollTrigger plugin is lib/lenis.ts's job (it runs as a
// side effect of importing prefersReducedMotion below) -- this module just
// uses the "scrollTrigger" config key, no direct reference to the plugin.
import { prefersReducedMotion } from "../lib/lenis";

/** [data-reveal] descendants, plus the container itself when it carries the attribute directly (e.g. Nav, which has nothing to wrap it). */
function queryRevealTargets(container: HTMLElement): HTMLElement[] {
  const targets = Array.from(container.querySelectorAll<HTMLElement>("[data-reveal]"));
  if (container.hasAttribute("data-reveal")) targets.unshift(container);
  return targets;
}

interface ScrollRevealOptions {
  /** Seconds between each staggered child's reveal. */
  stagger?: number;
  /** ScrollTrigger "start" position; ignored when `immediate` is set. */
  start?: string;
  /** Play on mount instead of on scroll-into-view -- use for above-the-fold content. */
  immediate?: boolean;
  /** Delay (seconds) before an immediate reveal starts. */
  delay?: number;
}

/**
 * Reveals every `[data-reveal]` descendant of the returned ref with a
 * staggered fade + rise, driven entirely by GSAP (+ ScrollTrigger for the
 * scroll-into-view case). Respects prefers-reduced-motion by skipping
 * straight to the resolved state.
 */
export function useScrollReveal<T extends HTMLElement>(options: ScrollRevealOptions = {}) {
  const containerRef = useRef<T | null>(null);
  const { stagger = 0.09, start = "top 82%", immediate = false, delay = 0 } = options;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const items = queryRevealTargets(container);
    if (!items.length) return;

    if (prefersReducedMotion()) {
      gsap.set(items, { opacity: 1, y: 0 });
      return;
    }

    const ctx = gsap.context(() => {
      const vars: gsap.TweenVars = {
        opacity: 1,
        y: 0,
        duration: 0.9,
        ease: "power3.out",
        stagger,
      };

      if (immediate) {
        gsap.to(items, { ...vars, delay });
      } else {
        gsap.to(items, {
          ...vars,
          scrollTrigger: { trigger: container, start, once: true },
        });
      }
    }, container);

    return () => ctx.revert();
  }, [stagger, start, immediate, delay]);

  return containerRef;
}
