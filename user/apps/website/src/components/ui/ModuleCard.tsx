import type { ModuleIconName } from "../../types/content";
import { ModuleIcon } from "./ModuleIcon";
import styles from "./ModuleCard.module.css";

interface ModuleCardProps {
  title: string;
  description: string;
  icon: ModuleIconName;
}

// No data-reveal attribute here on purpose -- this grid renders statically,
// no scroll animation, per an explicit request to keep it non-animated.
export function ModuleCard({ title, description, icon }: ModuleCardProps) {
  return (
    <article className={styles.card}>
      <div className={styles.icon}>
        <ModuleIcon name={icon} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
    </article>
  );
}
