import { Trans, useTranslation } from "react-i18next";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { Button } from "../ui/Button";
import { Starfield } from "../ui/Starfield";
import styles from "./Hero.module.css";

export function Hero() {
  const sectionRef = useScrollReveal<HTMLElement>({ immediate: true, delay: 0.15, stagger: 0.1 });
  const { t } = useTranslation();

  return (
    <section ref={sectionRef} className={styles.hero}>
      <div className={styles.field} aria-hidden="true">
        <Starfield />
        <div className={styles.glow} />
      </div>

      <div className={styles.content}>
        <p className="kicker" data-reveal>
          {t("hero.kicker")}
        </p>
        <h1 className={styles.title} data-reveal>
          {t("hero.titleLine1")}
          <br />
          <Trans i18nKey="hero.titleLine2" components={{ em: <em /> }} />
          <br />
          {t("hero.titleLine3")}
        </h1>
        <p className={styles.sub} data-reveal>
          {t("hero.sub")}
        </p>
        <div className={styles.actions} data-reveal>
          <Button href="#download" size="lg">
            {t("hero.ctaDownload")}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path
                d="M8 1v10m0 0L4 7m4 4l4-4M2 14h12"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Button>
          <Button href="#features" variant="ghost" size="lg">
            {t("hero.ctaFeatures")}
          </Button>
        </div>
        <p className={styles.meta} data-reveal>
          {t("hero.meta")}
        </p>
      </div>
    </section>
  );
}
