import { useTranslation } from "react-i18next";
import { modules } from "../../data/modules";
import { useScrollReveal } from "../../hooks/useScrollReveal";
import { ModuleCard } from "../ui/ModuleCard";
import { SectionHeading } from "../ui/SectionHeading";
import { CapabilityList } from "./CapabilityList";
import styles from "./Features.module.css";

export function Features() {
  const sectionRef = useScrollReveal<HTMLElement>();
  const { t } = useTranslation();

  return (
    <section id="features" ref={sectionRef} className="section">
      <SectionHeading kicker={t("features.kicker")}>
        {t("features.headingLine1", { count: modules.length })}
        <br />
        {t("features.headingLine2")}
      </SectionHeading>

      {/* Static grid, no scroll-reveal -- deliberately, so a big list stays quick to scan. */}
      <div className={styles.grid}>
        {modules.map((module) => (
          <ModuleCard
            key={module.id}
            icon={module.icon}
            title={t(`modules.${module.id}.title`)}
            description={t(`modules.${module.id}.description`)}
          />
        ))}
      </div>

      <CapabilityList />
    </section>
  );
}
