import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "../../lib/lenis";
import styles from "./Starfield.module.css";

interface Star {
  x: number;
  y: number;
  r: number;
  a: number;
  twinkleSpeed: number;
  phase: number;
  /** Depth-based drift: bigger/closer stars drift faster, for a gentle parallax feel. */
  driftX: number;
  driftY: number;
}

/** Twinkling + slowly drifting starfield for the hero background. Pure canvas, no dependency. */
export function Starfield() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const reduceMotion = prefersReducedMotion();
    let stars: Star[] = [];
    let width = 0;
    let height = 0;
    let frameId = 0;

    function makeStar(): Star {
      const depth = Math.random(); // 0 = far/small/slow, 1 = near/big/fast
      const angle = Math.PI / 2 + (Math.random() - 0.5) * 0.6; // mostly-downward drift, andromeda-drift feel
      const driftMagnitude = 0.02 + depth * 0.16;
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        r: 0.3 + depth * 1.3,
        a: Math.random() * 0.6 + 0.2,
        twinkleSpeed: Math.random() * 0.15 + 0.02,
        phase: Math.random() * Math.PI * 2,
        driftX: Math.cos(angle) * driftMagnitude,
        driftY: Math.sin(angle) * driftMagnitude,
      };
    }

    function resize() {
      width = canvas!.width = canvas!.offsetWidth * devicePixelRatio;
      height = canvas!.height = canvas!.offsetHeight * devicePixelRatio;
      const count = Math.floor((width * height) / 9000);
      stars = Array.from({ length: count }, makeStar);
    }

    function draw(time: number) {
      ctx!.clearRect(0, 0, width, height);
      for (const s of stars) {
        if (!reduceMotion) {
          s.x += s.driftX;
          s.y += s.driftY;
          // wrap around edges so the field feels infinite, not like it's draining off-screen
          if (s.x < -5) s.x = width + 5;
          if (s.x > width + 5) s.x = -5;
          if (s.y < -5) s.y = height + 5;
          if (s.y > height + 5) s.y = -5;
        }

        const twinkle = reduceMotion ? s.a : s.a + Math.sin(time * 0.001 * s.twinkleSpeed + s.phase) * 0.25;
        ctx!.beginPath();
        ctx!.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(243, 243, 240, ${Math.max(0, twinkle)})`;
        ctx!.fill();
      }
      if (!reduceMotion) frameId = requestAnimationFrame(draw);
    }

    resize();
    frameId = requestAnimationFrame(draw);
    window.addEventListener("resize", resize);

    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvasRef} className={styles.canvas} aria-hidden="true" />;
}
