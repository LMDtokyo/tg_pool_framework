import type { MouseEvent, ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { scrollToHash } from "../../lib/lenis";
import styles from "./Button.module.css";

type Variant = "primary" | "ghost";
type Size = "sm" | "lg" | "xl" | "block";

interface ButtonProps {
  href: string;
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  className?: string;
}

const EXTERNAL_PREFIXES = ["http://", "https://", "mailto:", "tel:"];

/**
 * Anchor styled as a button.
 * - "#hash" smooth-scrolls on the landing page, routing to "/" first if needed.
 * - "/path" uses client-side routing (no full reload).
 * - anything else (external URLs, mailto, tel) navigates normally.
 */
export function Button({ href, children, variant = "primary", size = "lg", className }: ButtonProps) {
  const navigate = useNavigate();
  const location = useLocation();

  // href="#" alone is a placeholder (real download/checkout links aren't wired up
  // yet) -- querySelector("#") throws, so only treat it as an in-page anchor once
  // there's an actual id after the hash.
  const isInPageLink = href.startsWith("#") && href.length > 1;
  const isExternal = EXTERNAL_PREFIXES.some((prefix) => href.startsWith(prefix));
  const isInternalRoute = !isInPageLink && !isExternal && href.startsWith("/");

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (isInPageLink) {
      event.preventDefault();
      if (location.pathname !== "/") {
        navigate(`/${href}`);
      } else {
        scrollToHash(href);
      }
      return;
    }
    if (isInternalRoute) {
      event.preventDefault();
      navigate(href);
    }
  };

  const classes = [styles.btn, styles[variant], styles[size], className].filter(Boolean).join(" ");

  return (
    <a href={href} onClick={handleClick} className={classes}>
      {children}
    </a>
  );
}
