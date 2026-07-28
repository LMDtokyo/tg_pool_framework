import styles from "./FaqItem.module.css";

interface FaqItemProps {
  question: string;
  answer: string;
  openByDefault?: boolean;
}

export function FaqItem({ question, answer, openByDefault }: FaqItemProps) {
  return (
    <details className={styles.item} open={openByDefault} data-reveal>
      <summary>{question}</summary>
      <p>{answer}</p>
    </details>
  );
}
