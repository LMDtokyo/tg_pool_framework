import { useTranslation } from "react-i18next";
import { navLinks } from "../../data/nav";
import { documentLinks, socialLinks } from "../../data/footer";
import { ScrollLink } from "../ui/ScrollLink";
import { Logo } from "./Logo";
import styles from "./Footer.module.css";

export function Footer() {
  const { t } = useTranslation();

  return (
    <footer className={styles.footer}>
      <div className={styles.columns}>
        <div className={styles.brandColumn}>
          <Logo />
          <p className={styles.tagline}>{t("footer.tagline")}</p>
        </div>

        <div className={styles.column}>
          <p className={styles.heading}>{t("footer.navHeading")}</p>
          <ul>
            {navLinks.map((link) => (
              <li key={link.id}>
                <ScrollLink href={link.href}>{t(`nav.${link.id}`)}</ScrollLink>
              </li>
            ))}
          </ul>
        </div>

        <div className={styles.column}>
          <p className={styles.heading}>{t("footer.socialHeading")}</p>
          <ul>
            {socialLinks.map((link) => (
              <li key={link.id}>
                <a href={link.href} target="_blank" rel="noreferrer">
                  {t(`footer.social.${link.id}`)}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <div className={styles.column}>
          <p className={styles.heading}>{t("footer.docsHeading")}</p>
          <ul>
            {documentLinks.map((link) => (
              <li key={link.id}>
                <a href={link.href}>{t(`footer.docs.${link.id}`)}</a>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className={styles.bottom}>
        <span>{t("footer.copyright")}</span>
        <span className={styles.disclaimer}>{t("footer.disclaimer")}</span>
      </div>
    </footer>
  );
}
