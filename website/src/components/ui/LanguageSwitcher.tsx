import { useTranslation } from "react-i18next";
import { languages } from "../../i18n/languages";
import styles from "./LanguageSwitcher.module.css";

export function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const current = i18n.resolvedLanguage ?? i18n.language;

  return (
    <div className={styles.switcher} role="group" aria-label="Language">
      {languages.map((lang) => (
        <button
          key={lang.code}
          type="button"
          className={current === lang.code ? styles.active : undefined}
          onClick={() => i18n.changeLanguage(lang.code)}
          aria-pressed={current === lang.code}
        >
          {lang.nativeLabel}
        </button>
      ))}
    </div>
  );
}
