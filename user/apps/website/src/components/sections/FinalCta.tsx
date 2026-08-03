import { useTranslation } from "react-i18next";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { Button } from "../ui/Button";
import styles from "./FinalCta.module.css";

export function FinalCta() {
  const sectionRef = useScrollReveal<HTMLElement>();
  const { t } = useTranslation();

  return (
    <section id="download" ref={sectionRef} className={styles.cta}>
      <h2 className={styles.title} data-reveal>
        {t("finalCta.titleLine1")}
        <br />
        {t("finalCta.titleLine2")}
      </h2>
      <p className={styles.sub} data-reveal>
        {t("finalCta.sub")}
      </p>
      <div data-reveal>
        <Button href="#" size="xl">
          {t("finalCta.cta")}
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M8 1v10m0 0L4 7m4 4l4-4M2 14h12"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </Button>
      </div>
    </section>
  );
}
