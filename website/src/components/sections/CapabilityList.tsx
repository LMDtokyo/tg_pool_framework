import { useTranslation } from "react-i18next";
import { capabilityCategories } from "../../data/capabilities";
import { CheckIcon } from "../ui/CheckIcon";
import styles from "./CapabilityList.module.css";

/** Dense, categorized checklist of what each module can configure/do --
 * complements the module grid above it, one level more granular. */
export function CapabilityList() {
  const { t } = useTranslation();

  return (
    <div className={styles.panel} data-reveal>
      <p className={styles.eyebrow}>{t("capabilities.eyebrow")}</p>
      <div className={styles.grid}>
        {capabilityCategories.map((category) => {
          const items = t(`capabilities.categories.${category.id}.items`, { returnObjects: true }) as string[];
          return (
            <div key={category.id} className={styles.column}>
              <h3>{t(`capabilities.categories.${category.id}.title`)}</h3>
              <ul>
                {items.map((item) => (
                  <li key={item}>
                    <span className={styles.check}>
                      <CheckIcon />
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
