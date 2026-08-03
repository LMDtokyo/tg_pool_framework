export interface LanguageOption {
  code: "ru" | "en" | "zh";
  nativeLabel: string;
}

export const languages: LanguageOption[] = [
  { code: "ru", nativeLabel: "RU" },
  { code: "en", nativeLabel: "EN" },
  { code: "zh", nativeLabel: "中文" },
];
