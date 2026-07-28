import type { ResolvedManualCategory } from "../../types/content";
import { ManualArticleCard } from "./ManualArticleCard";
import styles from "./ManualCategorySection.module.css";

export function ManualCategorySection({ id, title, articles }: ResolvedManualCategory) {
  return (
    <section id={id} className={styles.section}>
      <h2 className={styles.heading}>{title}</h2>
      <div className={styles.grid}>
        {articles.map((article) => (
          <ManualArticleCard key={article.slug} {...article} />
        ))}
      </div>
    </section>
  );
}
