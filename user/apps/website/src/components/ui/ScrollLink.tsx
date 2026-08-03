import type { MouseEvent, ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { scrollToHash } from "../../lib/lenis";

interface ScrollLinkProps {
  /** Landing-page anchor, e.g. "#features". */
  href: string;
  children: ReactNode;
  className?: string;
}

/** Anchor that smooth-scrolls to a landing-page section. From another page it
 * routes to "/" + the hash first; LandingPage picks up the hash on mount. */
export function ScrollLink({ href, children, className }: ScrollLinkProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    if (location.pathname !== "/") {
      navigate(`/${href}`);
      return;
    }
    scrollToHash(href);
  };

  return (
    <a href={`/${href}`} onClick={handleClick} className={className}>
      {children}
    </a>
  );
}
