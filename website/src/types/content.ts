export interface NavLinkItem {
  id: string;
  href: string;
}

export type ModuleIconName =
  | "dashboard"
  | "accounts"
  | "parsing"
  | "broadcast"
  | "invite"
  | "phone"
  | "shield"
  | "proxyPool"
  | "sms"
  | "marketplace"
  | "convert"
  | "fingerprint"
  | "shuffle"
  | "lock";

export interface ModuleItem {
  id: string;
  icon: ModuleIconName;
}

export interface ModuleContent {
  title: string;
  description: string;
}

export interface StepItem {
  id: string;
  number: string;
}

export interface StepContent {
  title: string;
  description: string;
}

export interface PricingTier {
  id: string;
  price: string;
  featured?: boolean;
}

export interface PricingTierContent {
  label: string;
  period: string;
  description: string;
}

export interface FaqEntry {
  id: string;
  openByDefault?: boolean;
}

export interface FaqEntryContent {
  question: string;
  answer: string;
}

export interface CapabilityCategory {
  id: string;
}

export interface CapabilityCategoryContent {
  title: string;
  items: string[];
}

export interface ManualArticle {
  slug: string;
  icon: ModuleIconName;
}

export interface ManualArticleContent {
  title: string;
  summary: string;
}

export interface ManualCategory {
  id: string;
  icon: ModuleIconName;
  articles: ManualArticle[];
}

export interface ManualCategoryContent {
  title: string;
}

export interface ResolvedManualArticle extends ManualArticle, ManualArticleContent {}

export interface ResolvedManualCategory extends Omit<ManualCategory, "articles"> {
  title: string;
  articles: ResolvedManualArticle[];
}
