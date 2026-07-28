import styles from "./StepCard.module.css";

interface StepCardProps {
  number: string;
  title: string;
  description: string;
}

export function StepCard({ number, title, description }: StepCardProps) {
  return (
    <div className={styles.step} data-reveal>
      <span className={styles.number}>{number}</span>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
