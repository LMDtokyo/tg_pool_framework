import { useEffect } from "react";
import { destroyLenis, initLenis } from "../lib/lenis";

/** Starts the shared Lenis instance for the lifetime of the app. Call once, at the root. */
export function useLenis(): void {
  useEffect(() => {
    initLenis();
    return () => destroyLenis();
  }, []);
}
