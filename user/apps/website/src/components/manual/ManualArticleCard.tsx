import type { ResolvedManualArticle } from "../../types/content";
import { ModuleIcon } from "../ui/ModuleIcon";
import styles from "./ManualArticleCard.module.css";

export function ManualArticleCard({ title, icon, summary }: ResolvedManualArticle) {
  return (
    <article className={styles.card} title={summary}>
      <div className={styles.icon}>
        <ModuleIcon name={icon} />
      </div>
      <h3>{title}</h3>
    </article>
  );
}
