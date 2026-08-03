import type { ReactNode } from "react";
import styles from "./SectionHeading.module.css";

interface SectionHeadingProps {
  kicker: string;
  children: ReactNode;
}

export function SectionHeading({ kicker, children }: SectionHeadingProps) {
  return (
    <div className={styles.head}>
      <p className="kicker" data-reveal>
        {kicker}
      </p>
      <h2 className={styles.title} data-reveal>
        {children}
      </h2>
    </div>
  );
}
