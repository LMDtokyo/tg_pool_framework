import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";
import { navLinks } from "../../data/nav";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { Button } from "../ui/Button";
import { LanguageSwitcher } from "../ui/LanguageSwitcher";
import { ScrollLink } from "../ui/ScrollLink";
import { Logo } from "./Logo";
import styles from "./Nav.module.css";

export function Nav() {
  const navRef = useScrollReveal<HTMLElement>({ immediate: true, delay: 0.05 });
  const { t } = useTranslation();

  return (
    <header ref={navRef} className={styles.nav} data-reveal>
      <Logo />
      <nav className={styles.links}>
        {navLinks.map((link) => (
          <ScrollLink key={link.id} href={link.href}>
            {t(`nav.${link.id}`)}
          </ScrollLink>
        ))}
        <NavLink to="/manual" className={({ isActive }) => (isActive ? styles.activeLink : undefined)}>
          {t("nav.manual")}
        </NavLink>
      </nav>
      <div className={styles.actions}>
        <LanguageSwitcher />
        <Button href="#download" size="sm">
          {t("nav.download")}
        </Button>
      </div>
    </header>
  );
}
