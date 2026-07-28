import { useTranslation } from "react-i18next";
import { steps } from "../../data/steps";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { SectionHeading } from "../ui/SectionHeading";
import { StepCard } from "../ui/StepCard";
import styles from "./HowItWorks.module.css";

export function HowItWorks() {
  const sectionRef = useScrollReveal<HTMLElement>();
  const { t } = useTranslation();

  return (
    <section id="how" ref={sectionRef} className="section section-alt">
      <SectionHeading kicker={t("how.kicker")}>
        {t("how.headingLine1")}
        <br />
        {t("how.headingLine2")}
      </SectionHeading>

      <div className={styles.steps}>
        <div className={styles.line} aria-hidden="true" />
        {steps.map((step) => (
          <StepCard
            key={step.id}
            number={step.number}
            title={t(`steps.${step.id}.title`)}
            description={t(`steps.${step.id}.description`)}
          />
        ))}
      </div>
    </section>
  );
}
