import { useTranslation } from "react-i18next";
import styles from "./Marquee.module.css";

export function Marquee() {
  const { t } = useTranslation();
  const marqueeItems = t("marquee", { returnObjects: true }) as string[];
  // Duplicated once so the CSS keyframe can loop seamlessly on a -50% translate.
  const items = [...marqueeItems, ...marqueeItems];

  return (
    <div className={styles.marquee} aria-hidden="true">
      <div className={styles.track}>
        {items.map((item, index) => (
          <span key={`${item}-${index}`}>
            {item}
            <span className={styles.dot}>·</span>
          </span>
        ))}
      </div>
    </div>
  );
}
