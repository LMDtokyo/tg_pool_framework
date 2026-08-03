import { useEffect } from "react";
import { useTranslation } from "react-i18next";

/** Keeps <html lang>, the tab title, and the meta description in sync with the active language. */
export function useDocumentMeta() {
  const { t, i18n } = useTranslation();

  useEffect(() => {
    document.documentElement.lang = i18n.resolvedLanguage ?? i18n.language;
    document.title = t("meta.title");

    const description = document.querySelector('meta[name="description"]');
    if (description) description.setAttribute("content", t("meta.description"));
  }, [t, i18n.resolvedLanguage, i18n.language]);
}
