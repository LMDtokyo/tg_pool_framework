import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ContactBubble.module.css";

// Placeholder contact channels -- swap for real ones before publishing.
const CONTACT_HREFS = {
  telegram: "https://t.me/your_support_here",
  email: "mailto:sales@example.com",
};

export function ContactBubble() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.wrapper}>
      {open && (
        <div className={styles.card} role="dialog" aria-label={t("contactBubble.dialogLabel")}>
          <p className={styles.title}>{t("contactBubble.title")}</p>
          <div className={styles.links}>
            <a href={CONTACT_HREFS.telegram} target="_blank" rel="noreferrer">
              {t("contactBubble.telegram")}
            </a>
            <a href={CONTACT_HREFS.email} target="_blank" rel="noreferrer">
              {t("contactBubble.email")}
            </a>
          </div>
        </div>
      )}
      <button
        type="button"
        className={styles.toggle}
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? t("contactBubble.close") : t("contactBubble.open")}
        aria-expanded={open}
      >
        {open ? (
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path
              d="M3 9.5a6.5 6.5 0 1110 5.3L4 17l1.2-4A6.47 6.47 0 013 9.5z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
    </div>
  );
}
