import { useTranslation } from "react-i18next";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { Button } from "../ui/Button";
import styles from "./DemoCta.module.css";

export function DemoCta() {
  const sectionRef = useScrollReveal<HTMLElement>();
  const { t } = useTranslation();

  return (
    <section ref={sectionRef} className="section">
      <div className={styles.card} data-reveal>
        <div className={styles.glow} aria-hidden="true" />
        <div className={styles.highlight} aria-hidden="true" />
        <div className={styles.content}>
          <h2 className={styles.title}>{t("demoCta.title")}</h2>
          <p className={styles.sub}>{t("demoCta.sub")}</p>
          {/* mailto placeholder -- swap for a real support address/Telegram before publishing */}
          <Button href="mailto:sales@example.com">{t("demoCta.cta")}</Button>
        </div>
      </div>
    </section>
  );
}
