import type { ModuleContent, StepContent, PricingTierContent, FaqEntryContent, CapabilityCategoryContent, ManualArticleContent, ManualCategoryContent } from "../types/content";

export interface Dictionary {
  meta: {
    title: string;
    description: string;
  };
  nav: {
    features: string;
    how: string;
    pricing: string;
    faq: string;
    manual: string;
    download: string;
  };
  hero: {
    kicker: string;
    titleLine1: string;
    titleLine2: string;
    titleLine3: string;
    sub: string;
    ctaDownload: string;
    ctaFeatures: string;
    meta: string;
  };
  marquee: string[];
  features: {
    kicker: string;
    headingLine1: string;
    headingLine2: string;
  };
  modules: {
    dashboard: ModuleContent;
    accounts: ModuleContent;
    parsing: ModuleContent;
    "send-by-id": ModuleContent;
    "send-by-numbers": ModuleContent;
    invite: ModuleContent;
    "number-checker": ModuleContent;
    proxy: ModuleContent;
    "proxy-pool": ModuleContent;
    "hero-sms": ModuleContent;
    smspool: ModuleContent;
    grizzlysms: ModuleContent;
    datamoll: ModuleContent;
    "tdata-to-session": ModuleContent;
    "session-to-tdata": ModuleContent;
    fingerprint: ModuleContent;
    randomizer: ModuleContent;
    license: ModuleContent;
  };
  capabilities: {
    eyebrow: string;
    categories: {
      parsing: CapabilityCategoryContent;
      sending: CapabilityCategoryContent;
      accounts: CapabilityCategoryContent;
      security: CapabilityCategoryContent;
      platform: CapabilityCategoryContent;
    };
  };
  how: {
    kicker: string;
    headingLine1: string;
    headingLine2: string;
  };
  steps: {
    connect: StepContent;
    collect: StepContent;
    send: StepContent;
    monitor: StepContent;
  };
  pricing: {
    kicker: string;
    headingLine1: string;
    headingLine2: string;
    note: string;
    choose: string;
    featuredBadge: string;
    tiers: {
      week: PricingTierContent;
      month: PricingTierContent;
      "half-year": PricingTierContent;
      year: PricingTierContent;
    };
  };
  demoCta: {
    title: string;
    sub: string;
    cta: string;
  };
  faq: {
    kicker: string;
    headingLine1: string;
    headingLine2: string;
    entries: {
      "windows-versions": FaqEntryContent;
      "device-change": FaqEntryContent;
      "activation-speed": FaqEntryContent;
      "account-safety": FaqEntryContent;
    };
  };
  finalCta: {
    titleLine1: string;
    titleLine2: string;
    sub: string;
    cta: string;
  };
  manual: {
    kicker: string;
    heading: string;
    sub: string;
    sidebarEyebrow: string;
    sidebarAriaLabel: string;
    categories: {
      setup: ManualCategoryContent & { articles: { "first-launch": ManualArticleContent; "license-activation": ManualArticleContent } };
      "accounts-panel": ManualCategoryContent & {
        articles: {
          "import-search": ManualArticleContent;
          "bulk-recheck": ManualArticleContent;
          "fingerprint-generator": ManualArticleContent;
          "tdata-to-session": ManualArticleContent;
          "session-to-tdata": ManualArticleContent;
          "open-session-folder": ManualArticleContent;
        };
      };
      "auto-registration": ManualCategoryContent & {
        articles: {
          "hero-sms": ManualArticleContent;
          smspool: ManualArticleContent;
          grizzlysms: ManualArticleContent;
          datamoll: ManualArticleContent;
        };
      };
      audience: ManualCategoryContent & {
        articles: {
          "auto-strategy": ManualArticleContent;
          "audience-filters": ManualArticleContent;
          "export-results": ManualArticleContent;
        };
      };
      sending: ManualCategoryContent & {
        articles: {
          "send-by-id": ManualArticleContent;
          "send-by-numbers": ManualArticleContent;
          "text-randomizer": ManualArticleContent;
        };
      };
      invite: ManualCategoryContent & { articles: { "invite-by-number": ManualArticleContent } };
      proxy: ManualCategoryContent & { articles: { "proxy-manager": ManualArticleContent; "proxy-pool-checker": ManualArticleContent } };
    };
  };
  footer: {
    tagline: string;
    navHeading: string;
    socialHeading: string;
    docsHeading: string;
    social: { channel: string; support: string };
    docs: { privacy: string; terms: string; offer: string };
    copyright: string;
    disclaimer: string;
  };
  cookieConsent: {
    dialogLabel: string;
    message: string;
    accept: string;
  };
  contactBubble: {
    dialogLabel: string;
    title: string;
    telegram: string;
    email: string;
    open: string;
    close: string;
  };
  scrollToTop: {
    label: string;
  };
}
