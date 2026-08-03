import type { ReactNode } from "react";
import { useDocumentMeta } from "../../hooks/useDocumentMeta";
import { useLenis } from "../../hooks/useLenis";
import { Nav } from "./Nav";
import { Footer } from "./Footer";
import { CookieConsent } from "../ui/CookieConsent";
import { ScrollToTop } from "../ui/ScrollToTop";
import { ContactBubble } from "../ui/ContactBubble";

/** Chrome shared by every page: nav, footer, and the floating widgets. */
export function Layout({ children }: { children: ReactNode }) {
  useLenis();
  useDocumentMeta();

  return (
    <>
      <div className="grain" aria-hidden="true" />
      <div className="ambient-glow" aria-hidden="true" />

      <Nav />
      {children}
      <Footer />

      <ScrollToTop />
      <ContactBubble />
      <CookieConsent />
    </>
  );
}
