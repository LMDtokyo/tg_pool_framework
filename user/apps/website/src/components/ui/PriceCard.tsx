import { useTranslation } from "react-i18next";
import { Button } from "./Button";
import styles from "./PriceCard.module.css";

interface PriceCardProps {
  label: string;
  price: string;
  period: string;
  description: string;
  featured?: boolean;
}

export function PriceCard({ label, price, period, description, featured }: PriceCardProps) {
  const { t } = useTranslation();
  const classes = [styles.card, featured && styles.featured].filter(Boolean).join(" ");

  return (
    <div className={classes} data-reveal>
      {featured && <span className={styles.badge}>{t("pricing.featuredBadge")}</span>}
      <p className={styles.label}>{label}</p>
      <p className={styles.price}>
        {price}
        <span>{period}</span>
      </p>
      <p className={styles.description}>{description}</p>
      <Button href="#" variant={featured ? "primary" : "ghost"} size="block">
        {t("pricing.choose")}
      </Button>
    </div>
  );
}
