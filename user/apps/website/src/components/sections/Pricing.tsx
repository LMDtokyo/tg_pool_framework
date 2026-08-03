import { useTranslation } from "react-i18next";
import { pricingTiers } from "../../data/pricing";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { PriceCard } from "../ui/PriceCard";
import { SectionHeading } from "../ui/SectionHeading";
import styles from "./Pricing.module.css";

export function Pricing() {
  const sectionRef = useScrollReveal<HTMLElement>();
  const { t } = useTranslation();

  return (
    <section id="pricing" ref={sectionRef} className="section">
      <SectionHeading kicker={t("pricing.kicker")}>
        {t("pricing.headingLine1")}
        <br />
        {t("pricing.headingLine2")}
      </SectionHeading>

      <div className={styles.grid}>
        {pricingTiers.map((tier) => (
          <PriceCard
            key={tier.id}
            price={tier.price}
            featured={tier.featured}
            label={t(`pricing.tiers.${tier.id}.label`)}
            period={t(`pricing.tiers.${tier.id}.period`)}
            description={t(`pricing.tiers.${tier.id}.description`)}
          />
        ))}
      </div>

      <p className={styles.note}>{t("pricing.note")}</p>
    </section>
  );
}
