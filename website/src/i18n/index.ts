import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { ru } from "./locales/ru";
import { en } from "./locales/en";
import { zh } from "./locales/zh";

const COOKIE_DAYS = 180;

i18next
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      en: { translation: en },
      zh: { translation: zh },
    },
    fallbackLng: "ru",
    supportedLngs: ["ru", "en", "zh"],
    load: "languageOnly",
    interpolation: { escapeValue: false },
    detection: {
      order: ["cookie", "navigator"],
      caches: ["cookie"],
      lookupCookie: "andromeda_lang",
      cookieMinutes: COOKIE_DAYS * 24 * 60,
      cookieOptions: { path: "/", sameSite: "lax" },
    },
  });

export default i18next;
