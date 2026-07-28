import type { MouseEvent } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ResolvedManualCategory } from "../../types/content";
import styles from "./ManualSidebar.module.css";

interface ManualSidebarProps {
  categories: ResolvedManualCategory[];
}

export function ManualSidebar({ categories }: ManualSidebarProps) {
  const { t } = useTranslation();
  const [activeId, setActiveId] = useState(categories[0]?.id);

  useEffect(() => {
    const sections = categories
      .map((category) => document.getElementById(category.id))
      .filter((el): el is HTMLElement => el !== null);

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length === 0) return;
        const topmost = visible.reduce((a, b) => (a.boundingClientRect.top < b.boundingClientRect.top ? a : b));
        setActiveId(topmost.target.id);
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: 0 },
    );

    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [categories]);

  const handleClick = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    event.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <nav className={styles.sidebar} aria-label={t("manual.sidebarAriaLabel")}>
      <p className={styles.eyebrow}>{t("manual.sidebarEyebrow")}</p>
      <ul>
        {categories.map((category) => (
          <li key={category.id}>
            <a
              href={`#${category.id}`}
              className={category.id === activeId ? styles.active : undefined}
              onClick={(event) => handleClick(event, category.id)}
            >
              {category.title}
              <span className={styles.count}>{category.articles.length}</span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
