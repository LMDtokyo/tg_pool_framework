import { useTranslation } from "react-i18next";
import { manualCategories } from "../data/manual";
import { ManualCategorySection } from "../components/manual/ManualCategorySection";
import { ManualSidebar } from "../components/manual/ManualSidebar";
import type { ResolvedManualCategory } from "../types/content";
import styles from "./ManualPage.module.css";

export function ManualPage() {
  const { t } = useTranslation();

  const categories: ResolvedManualCategory[] = manualCategories.map((category) => ({
    id: category.id,
    icon: category.icon,
    title: t(`manual.categories.${category.id}.title`),
    articles: category.articles.map((article) => ({
      slug: article.slug,
      icon: article.icon,
      title: t(`manual.categories.${category.id}.articles.${article.slug}.title`),
      summary: t(`manual.categories.${category.id}.articles.${article.slug}.summary`),
    })),
  }));

  return (
    <main className={styles.page}>
      <div className={styles.head}>
        <p className="kicker">{t("manual.kicker")}</p>
        <h1>{t("manual.heading")}</h1>
        <p className={styles.sub}>{t("manual.sub", { count: categories.length })}</p>
      </div>
      <div className={styles.layout}>
        <ManualSidebar categories={categories} />
        <div className={styles.content}>
          {categories.map((category) => (
            <ManualCategorySection key={category.id} {...category} />
          ))}
        </div>
      </div>
    </main>
  );
}
