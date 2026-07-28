import type { Dictionary } from "../schema";

export const en: Dictionary = {
  meta: {
    title: "Telegram Andromeda — Telegram account fleet management",
    description: "Audience parsing, mass broadcasts, an account pool, and monitoring — in one Windows application.",
  },
  nav: {
    features: "Features",
    how: "How it works",
    pricing: "Pricing",
    faq: "FAQ",
    manual: "Manual",
    download: "Download",
  },
  hero: {
    kicker: "TELEGRAM FLEET MANAGEMENT · FOR WINDOWS",
    titleLine1: "One control panel",
    titleLine2: "for your <em>entire</em>",
    titleLine3: "Telegram fleet",
    sub: "Audience parsing, mass broadcasts, account warm-up, and pool monitoring — in one application. No manual routine, and no risk of taking down the whole pool with a single mistake.",
    ctaDownload: "Download for Windows",
    ctaFeatures: "See features",
    meta: "Windows 10/11 · Hardware-based activation · Feature updates included in the license",
  },
  marquee: ["AUDIENCE PARSING", "MASS BROADCASTS", "ACCOUNT POOL", "NUMBER CHECKING", "PROXY MANAGER", "ANTI-FLOOD"],
  features: {
    kicker: "FEATURES",
    headingLine1: "{{count}} modules",
    headingLine2: "for every use case",
  },
  modules: {
    dashboard: {
      title: "Dashboard",
      description: "A real-time overview of the pool: account statuses and a live event feed.",
    },
    accounts: {
      title: "Accounts",
      description: "A single registry of the whole pool: status, geo, role, proxy, quick search and filters.",
    },
    parsing: {
      title: "Parsing",
      description: "Collect audiences from chats, channels, and topics — with filters and a smart auto-strategy.",
    },
    "send-by-id": {
      title: "Send by ID",
      description: "Bulk delivery of text, media, and reposts across a list of recipients.",
    },
    "send-by-numbers": {
      title: "Send by phone number",
      description: "The same sending engine — only recipients are given as phone numbers.",
    },
    invite: {
      title: "Invite by phone number",
      description: "Bulk-invite an audience into your chats and channels.",
    },
    "number-checker": {
      title: "Number checker",
      description: "Quickly check a list of phone numbers for a Telegram account.",
    },
    proxy: {
      title: "Proxy",
      description: "Store and check proxy lists, and clear out dead ones in a click.",
    },
    "proxy-pool": {
      title: "Proxy pool checker",
      description: "Verify rotation quality: how many genuinely distinct IPs a provider actually hands out.",
    },
    "hero-sms": {
      title: "Hero SMS",
      description: "Automatic registration of new accounts through the Hero SMS provider.",
    },
    smspool: {
      title: "SMSpool",
      description: "The same, through the SMSpool provider.",
    },
    grizzlysms: {
      title: "GrizzlySMS",
      description: "The same, through the GrizzlySMS provider.",
    },
    datamoll: {
      title: "Datamoll",
      description: "Top up the pool with ready-made accounts from the Datamoll marketplace.",
    },
    "tdata-to-session": {
      title: "Tdata → Session",
      description: "Convert Telegram Desktop folders into session files for the pool.",
    },
    "session-to-tdata": {
      title: "Session → Tdata",
      description: "The reverse conversion — session back into Telegram Desktop format.",
    },
    fingerprint: {
      title: "Fingerprint generator",
      description: "A unique digital device profile for every account.",
    },
    randomizer: {
      title: "Text randomizer",
      description: "Automatic template-based uniquing of broadcast text.",
    },
    license: {
      title: "License activation",
      description: "Bind your subscription to hardware through a dedicated activator.",
    },
  },
  capabilities: {
    eyebrow: "And that's far from everything",
    categories: {
      parsing: {
        title: "Parsing",
        items: [
          "Auto-strategy combines sources on its own for every group",
          "Members, comments, reactions, polls, system events, forum topics",
          "Filters: activity, gender, avatar, Premium, bots",
          "Pick sources from chats you've already joined in one click",
          "Sharding — the whole pool collects in parallel",
          "Export to Excel, SQLite, and a readable .txt",
        ],
      },
      sending: {
        title: "Broadcasts",
        items: [
          "By ID and by phone number",
          "Spintax, media, reposts from a channel or Postbot",
          "Scheduled sending and repeating cycles",
          "Auto-stop on bans, spam-blocks, flood waves",
          "Stream management — several accounts at once",
          "Several independent ways to find the recipient",
        ],
      },
      accounts: {
        title: "Accounts & sessions",
        items: [
          "One table: status, geo, role, folder, usage",
          "Bulk number checking before a campaign",
          "Convert tdata into session files",
          "Import .session + .json pairs",
          "Open an account's session file in one click",
          "Bulk pool rescan",
        ],
      },
      security: {
        title: "Proxy & security",
        items: [
          "Proxy list manager and checker",
          "Bind a proxy to a specific account",
          "A unique digital device fingerprint per account",
          "Session file encryption",
          "Account isolation — no session conflicts",
        ],
      },
      platform: {
        title: "Platform",
        items: [
          "Interface in Russian, English, and Chinese",
          "A live real-time event feed",
          "Hardware-bound license",
          "Portable install — nothing written to the system",
          "Feature updates included in the subscription",
        ],
      },
    },
  },
  how: {
    kicker: "PROCESS",
    headingLine1: "From install to your first",
    headingLine2: "broadcast — four steps",
  },
  steps: {
    connect: {
      title: "Connect your accounts",
      description: "Import .session files or convert tdata — with a proxy and digital fingerprint for every account.",
    },
    collect: {
      title: "Collect an audience",
      description: "Pick a source, enable smart parsing, filter by gender, activity, and Premium status.",
    },
    send: {
      title: "Launch a broadcast",
      description: "Spintax text, media, scheduling, load-sharing across pool accounts — with auto-stop on bans.",
    },
    monitor: {
      title: "Watch the pool",
      description: "A live event feed, real-time statuses, export results to SQLite / Excel / text.",
    },
  },
  pricing: {
    kicker: "PRICING",
    headingLine1: "The same software.",
    headingLine2: "Just pick a term.",
    note: "Prices are placeholders for layout — replace with real ones before publishing.",
    choose: "Choose",
    featuredBadge: "Best value",
    tiers: {
      week: { label: "Week", period: "/wk", description: "Test the pool once at your own volumes." },
      month: { label: "Month", period: "/mo", description: "The standard tier for ongoing work." },
      "half-year": {
        label: "6 months",
        period: "/6 mo",
        description: "For teams already warming up the pool at scale.",
      },
      year: { label: "Year", period: "/yr", description: "The longest term, the lowest monthly price." },
    },
  },
  demoCta: {
    title: "Not sure what fits you?",
    sub: "Write to us — we'll walk you through a plan for your volumes and give a quick demo.",
    cta: "Contact us",
  },
  faq: {
    kicker: "QUESTIONS",
    headingLine1: "A quick rundown of",
    headingLine2: "what matters before you start",
    entries: {
      "windows-versions": {
        question: "Which Windows versions are supported?",
        answer:
          "Windows 10 and Windows 11, 64-bit. The install is portable — all data is stored next to the application, nothing is written to system folders.",
      },
      "device-change": {
        question: "What happens if I change computers?",
        answer:
          "The license is hardware-bound. Contact support — re-binding to a new device is done manually and free of charge within reasonable limits.",
      },
      "activation-speed": {
        question: "How fast do I get access after paying?",
        answer:
          "The activation key is issued right after payment. Activation runs through a separate console activator, with no reinstall of the main application.",
      },
      "account-safety": {
        question: "How safe is this for the accounts?",
        answer:
          "Every account gets its own digital device fingerprint and, if you want, its own proxy. Broadcasts respect pauses, limits, and auto-stop at the first signs of a ban, instead of just hammering away to the end.",
      },
    },
  },
  finalCta: {
    titleLine1: "Ready to take the pool",
    titleLine2: "under full control?",
    sub: "Download the app and activate your license in a couple of minutes.",
    cta: "Download Telegram Andromeda",
  },
  manual: {
    kicker: "MANUAL",
    heading: "Telegram Andromeda knowledge base",
    sub: "All {{count}} sections of the pool in one place — from the first launch to fine-tuning broadcasts and audience collection.",
    sidebarEyebrow: "Categories",
    sidebarAriaLabel: "Manual categories",
    categories: {
      setup: {
        title: "Installation & setup",
        articles: {
          "first-launch": {
            title: "First launch",
            summary:
              "The install is portable: everything the program reads and writes lives next to the app in the Data folder — nothing is scattered across system folders, and it's easy to move to another PC by copying.",
          },
          "license-activation": {
            title: "License activation",
            summary:
              "The activation key is bound to the hardware through a separate console activator — enter it once, and the app periodically re-confirms the license on its own after that.",
          },
        },
      },
      "accounts-panel": {
        title: "Accounts panel",
        articles: {
          "import-search": {
            title: "Import & search accounts",
            summary: "Import .session files or .session+.json pairs, then search and filter the pool by status, geo, role, and folder in one table.",
          },
          "bulk-recheck": {
            title: "Bulk check",
            summary: "Select the accounts you need and refresh their status (alive, banned, unauthorized) with one button.",
          },
          "fingerprint-generator": {
            title: "Fingerprint generator",
            summary: "Creates a unique digital device profile for every session file — each account looks like a separate device.",
          },
          "tdata-to-session": {
            title: "Tdata → Session",
            summary: "Batch-converts Telegram Desktop folders into session files, ready to work in the pool.",
          },
          "session-to-tdata": {
            title: "Session → Tdata",
            summary: "The reverse conversion — turns a session back into a folder for Telegram Desktop.",
          },
          "open-session-folder": {
            title: "Open account session",
            summary: "One button in the accounts table opens a specific account's session file folder in Explorer.",
          },
        },
      },
      "auto-registration": {
        title: "Auto-registration",
        articles: {
          "hero-sms": {
            title: "Hero SMS",
            summary: "Buy numbers and automatically register new accounts through the Hero SMS provider, including receiving the 2FA code right in the app.",
          },
          smspool: {
            title: "SMSpool",
            summary: "The same registration flow through the SMSpool provider — a different price and number-availability model.",
          },
          grizzlysms: {
            title: "GrizzlySMS",
            summary: "The same registration flow through the GrizzlySMS provider.",
          },
          datamoll: {
            title: "Datamoll",
            summary: "Top up the pool with ready-made accounts from the Datamoll marketplace — no manual registration needed.",
          },
        },
      },
      audience: {
        title: "Audience collection",
        articles: {
          "auto-strategy": {
            title: "Smart auto-strategy",
            summary: "Automatically combines several collection sources for every group or channel, instead of relying on one source that might not show everyone.",
          },
          "audience-filters": {
            title: "Audience filters",
            summary: "Filter by gender, activity, avatar presence, Premium status, and exclude bots right at the collection stage.",
          },
          "export-results": {
            title: "Export results",
            summary: "Every run is saved separately — to Excel, SQLite, and a readable text list, with a report on how much and who was collected.",
          },
        },
      },
      sending: {
        title: "Broadcasts",
        articles: {
          "send-by-id": {
            title: "Send by ID",
            summary: "Text, media, and reposts — by a list of Telegram IDs or usernames, with scheduling and auto-stop at the first signs of a ban.",
          },
          "send-by-numbers": {
            title: "Send by phone number",
            summary: "The same sending engine, only recipients are given as a list of phone numbers.",
          },
          "text-randomizer": {
            title: "Text randomization",
            summary: "Uniques broadcast text from a template, so recipients don't see the exact same message word-for-word.",
          },
        },
      },
      invite: {
        title: "Invite",
        articles: {
          "invite-by-number": {
            title: "Invite by phone number",
            summary: "Bulk-invite an audience (by ID, username, or from a parsing export) into your chats and channels through linked sender accounts.",
          },
        },
      },
      proxy: {
        title: "Proxy",
        articles: {
          "proxy-manager": {
            title: "Proxy management",
            summary: "A store for HTTP/SOCKS5 lists: bulk adding, liveness checks, and clearing dead ones with one button.",
          },
          "proxy-pool-checker": {
            title: "Proxy pool checker",
            summary: "Runs requests through the proxies and counts unique outbound IPs, to see whether the provider is actually rotating addresses.",
          },
        },
      },
    },
  },
  footer: {
    tagline: "Telegram account fleet management for Windows.",
    navHeading: "Navigation",
    socialHeading: "Social",
    docsHeading: "Documents",
    social: { channel: "Telegram channel", support: "Support" },
    docs: { privacy: "Privacy Policy", terms: "Terms of Use", offer: "Public Offer" },
    copyright: "© 2026 Telegram Andromeda",
    disclaimer: "Not affiliated with Telegram Messenger Inc.",
  },
  cookieConsent: {
    dialogLabel: "Cookie notice",
    message: "We use cookies to improve the site. By continuing to use the site, you agree to their use.",
    accept: "Got it",
  },
  contactBubble: {
    dialogLabel: "Contact us",
    title: "Got questions?",
    telegram: "Message us on Telegram",
    email: "Email us",
    open: "Contact us",
    close: "Close contact window",
  },
  scrollToTop: {
    label: "Back to top",
  },
};
