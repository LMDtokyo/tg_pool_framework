import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getCookie, setCookie } from "../../lib/cookies";
import styles from "./CookieConsent.module.css";

const COOKIE_NAME = "andromeda_cookie_consent";
const COOKIE_DAYS = 180;

export function CookieConsent() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(() => getCookie(COOKIE_NAME) === "1");

  if (dismissed) return null;

  const accept = () => {
    setCookie(COOKIE_NAME, "1", COOKIE_DAYS);
    setDismissed(true);
  };

  return (
    <div className={styles.banner} role="dialog" aria-label={t("cookieConsent.dialogLabel")}>
      <p>{t("cookieConsent.message")}</p>
      <button type="button" className={styles.accept} onClick={accept}>
        {t("cookieConsent.accept")}
      </button>
    </div>
  );
}
