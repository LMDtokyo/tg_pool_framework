import { useTranslation } from "react-i18next";
import { faqEntries } from "../../data/faq";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { FaqItem } from "../ui/FaqItem";
import { SectionHeading } from "../ui/SectionHeading";
import styles from "./Faq.module.css";

export function Faq() {
  const sectionRef = useScrollReveal<HTMLElement>();
  const { t } = useTranslation();

  return (
    <section id="faq" ref={sectionRef} className="section section-alt">
      <SectionHeading kicker={t("faq.kicker")}>
        {t("faq.headingLine1")}
        <br />
        {t("faq.headingLine2")}
      </SectionHeading>

      <div className={styles.list}>
        {faqEntries.map((entry) => (
          <FaqItem
            key={entry.id}
            openByDefault={entry.openByDefault}
            question={t(`faq.entries.${entry.id}.question`)}
            answer={t(`faq.entries.${entry.id}.answer`)}
          />
        ))}
      </div>
    </section>
  );
}
