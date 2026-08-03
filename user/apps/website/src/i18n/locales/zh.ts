import type { Dictionary } from "../schema";

export const zh: Dictionary = {
  meta: {
    title: "Telegram Andromeda — Telegram 账号矩阵管理",
    description: "受众采集、批量群发、账号池与实时监控 — 集成于一款 Windows 应用。",
  },
  nav: {
    features: "功能",
    how: "工作流程",
    pricing: "价格",
    faq: "常见问题",
    manual: "使用手册",
    download: "下载",
  },
  hero: {
    kicker: "TELEGRAM 矩阵管理 · 仅限 WINDOWS",
    titleLine1: "一个控制台",
    titleLine2: "掌控您<em>全部</em>",
    titleLine3: "Telegram 账号矩阵",
    sub: "受众采集、批量群发、账号养号与账号池监控 — 全部集成在一款应用中。无需手动操作，也不会因为一次失误而导致整个账号池被封。",
    ctaDownload: "下载 Windows 版",
    ctaFeatures: "查看功能",
    meta: "Windows 10/11 · 硬件绑定激活 · 功能更新包含在授权内",
  },
  marquee: ["受众采集", "批量群发", "账号池", "号码检测", "代理管理", "防封防限"],
  features: {
    kicker: "功能",
    headingLine1: "{{count}} 个功能模块",
    headingLine2: "满足各种需求",
  },
  modules: {
    dashboard: {
      title: "仪表盘",
      description: "实时掌握账号池整体状况：账号状态与实时事件流。",
    },
    accounts: {
      title: "账号管理",
      description: "统一管理整个账号池：状态、地区、角色、代理，支持快速搜索与筛选。",
    },
    parsing: {
      title: "采集",
      description: "从群组、频道和话题中采集受众 — 配备筛选条件与智能自动策略。",
    },
    "send-by-id": {
      title: "按 ID 群发",
      description: "按收件人列表批量发送文本、媒体和转发内容。",
    },
    "send-by-numbers": {
      title: "按号码群发",
      description: "同一套群发引擎 — 只是收件人以电话号码指定。",
    },
    invite: {
      title: "按号码邀请",
      description: "批量将受众邀请进您的群组和频道。",
    },
    "number-checker": {
      title: "号码检测",
      description: "快速检测号码列表中哪些已注册 Telegram 账号。",
    },
    proxy: {
      title: "代理",
      description: "代理列表存储与检测，一键清理失效代理。",
    },
    "proxy-pool": {
      title: "代理池检测",
      description: "检测轮换质量：服务商实际提供了多少个不同 IP。",
    },
    "hero-sms": {
      title: "Hero SMS",
      description: "通过 Hero SMS 服务商自动注册新账号。",
    },
    smspool: {
      title: "SMSpool",
      description: "通过 SMSpool 服务商实现同样的功能。",
    },
    grizzlysms: {
      title: "GrizzlySMS",
      description: "通过 GrizzlySMS 服务商实现同样的功能。",
    },
    datamoll: {
      title: "Datamoll",
      description: "从 Datamoll 交易市场购入成品账号，补充账号池。",
    },
    "tdata-to-session": {
      title: "Tdata → Session",
      description: "将 Telegram Desktop 文件夹转换为账号池可用的 session 文件。",
    },
    "session-to-tdata": {
      title: "Session → Tdata",
      description: "反向转换 — 将 session 还原为 Telegram Desktop 格式。",
    },
    fingerprint: {
      title: "指纹生成器",
      description: "为每个账号生成独一无二的设备数字指纹。",
    },
    randomizer: {
      title: "文本随机化",
      description: "按模板自动对群发文本进行去重处理。",
    },
    license: {
      title: "授权激活",
      description: "通过独立激活器将订阅绑定到硬件。",
    },
  },
  capabilities: {
    eyebrow: "这还远远不是全部",
    categories: {
      parsing: {
        title: "采集",
        items: [
          "自动策略会为每个群组自动组合多种采集来源",
          "成员、评论、表情回应、投票、系统事件、论坛话题",
          "筛选条件：活跃度、性别、头像、Premium、机器人",
          "一键从已加入的群组中选择采集来源",
          "分片采集 — 整个账号池并行工作",
          "导出为 Excel、SQLite 和可读的 .txt 文件",
        ],
      },
      sending: {
        title: "群发",
        items: [
          "支持按 ID 和按电话号码",
          "Spintax 变体文本、媒体、来自频道或 Postbot 的转发",
          "定时发送与循环重复发送",
          "遇到封号、垃圾信息拦截、限流时自动停止",
          "多账号并发流管理",
          "多种独立方式查找收件人",
        ],
      },
      accounts: {
        title: "账号与会话",
        items: [
          "统一表格：状态、地区、角色、分组、使用情况",
          "投放前批量检测号码",
          "将 tdata 转换为 session 文件",
          "导入 .session + .json 文件对",
          "一键打开账号的 session 文件所在文件夹",
          "批量重新扫描账号池",
        ],
      },
      security: {
        title: "代理与安全",
        items: [
          "代理列表管理与检测",
          "将代理绑定到指定账号",
          "每个账号独立的设备数字指纹",
          "session 文件加密",
          "账号隔离 — 会话互不冲突",
        ],
      },
      platform: {
        title: "平台",
        items: [
          "支持俄语、英语和中文界面",
          "实时事件流",
          "硬件绑定授权",
          "便携式安装 — 不写入系统目录",
          "订阅内包含功能更新",
        ],
      },
    },
  },
  how: {
    kicker: "流程",
    headingLine1: "从安装到发出第一次",
    headingLine2: "群发，只需四步",
  },
  steps: {
    connect: {
      title: "接入账号",
      description: "导入 .session 文件或转换 tdata — 每个账号自带独立代理与设备指纹。",
    },
    collect: {
      title: "采集受众",
      description: "选择来源，开启智能采集，按性别、活跃度和 Premium 状态筛选。",
    },
    send: {
      title: "发起群发",
      description: "Spintax 变体文本、媒体、定时发送、账号池间负载分摊 — 遇到封号自动停止。",
    },
    monitor: {
      title: "监控账号池",
      description: "实时事件流、实时状态展示，支持导出结果至 SQLite / Excel / 文本文件。",
    },
  },
  pricing: {
    kicker: "价格",
    headingLine1: "同一套软件，",
    headingLine2: "只需选择订阅时长。",
    note: "当前价格为排版占位，正式发布前请替换为真实价格。",
    choose: "选择",
    featuredBadge: "最超值",
    tiers: {
      week: { label: "周卡", period: "/周", description: "按自己的量先测试一次账号池。" },
      month: { label: "月卡", period: "/月", description: "适合长期使用的标准套餐。" },
      "half-year": {
        label: "半年卡",
        period: "/半年",
        description: "适合已经批量运营账号池的团队。",
      },
      year: { label: "年卡", period: "/年", description: "时长最长，月均价格最低。" },
    },
  },
  demoCta: {
    title: "不确定哪个套餐适合您？",
    sub: "联系我们 — 我们会根据您的量级推荐合适的套餐，并提供简短演示。",
    cta: "联系我们",
  },
  faq: {
    kicker: "常见问题",
    headingLine1: "开始之前",
    headingLine2: "需要了解的几件事",
    entries: {
      "windows-versions": {
        question: "支持哪些 Windows 版本？",
        answer: "支持 Windows 10 和 Windows 11（64 位）。安装为便携版 — 所有数据都存放在程序目录下，不会写入系统目录。",
      },
      "device-change": {
        question: "更换电脑后怎么办？",
        answer: "授权与硬件绑定。请联系客服 — 在合理范围内，重新绑定到新设备为人工处理，且免费。",
      },
      "activation-speed": {
        question: "付款后多久能获得使用权限？",
        answer: "付款后立即发放激活密钥。激活通过独立的命令行激活器完成，无需重新安装主程序。",
      },
      "account-safety": {
        question: "这对账号安全性如何？",
        answer:
          "每个账号都有独立的设备数字指纹，如有需要还可配置独立代理。群发功能会遵循间隔与限额，并在出现封号迹象时自动停止，而不是一路发到账号被封为止。",
      },
    },
  },
  finalCta: {
    titleLine1: "准备好",
    titleLine2: "完全掌控您的账号池了吗？",
    sub: "下载应用并在几分钟内完成授权激活。",
    cta: "下载 Telegram Andromeda",
  },
  manual: {
    kicker: "使用手册",
    heading: "Telegram Andromeda 知识库",
    sub: "账号池的全部 {{count}} 个分类集中于此 — 从首次启动到群发与受众采集的精细设置。",
    sidebarEyebrow: "分类",
    sidebarAriaLabel: "手册分类",
    categories: {
      setup: {
        title: "安装与设置",
        articles: {
          "first-launch": {
            title: "首次启动",
            summary:
              "安装为便携版：程序读写的所有内容都存放在应用旁边的 Data 文件夹中 — 不会分散到系统目录，直接复制整个文件夹即可迁移到另一台电脑。",
          },
          "license-activation": {
            title: "授权激活",
            summary: "激活密钥通过独立的命令行激活器与硬件绑定 — 只需输入一次，此后应用会自动定期重新确认授权。",
          },
        },
      },
      "accounts-panel": {
        title: "账号面板",
        articles: {
          "import-search": {
            title: "导入与搜索账号",
            summary: "导入 .session 文件或 .session+.json 文件对，随后可在同一张表格中按状态、地区、角色和分组搜索、筛选账号池。",
          },
          "bulk-recheck": {
            title: "批量检测",
            summary: "勾选需要的账号，一键刷新其状态（存活、已封禁、未授权）。",
          },
          "fingerprint-generator": {
            title: "指纹生成器",
            summary: "为每个 session 文件生成独一无二的设备数字画像 — 让每个账号看起来都像是独立设备。",
          },
          "tdata-to-session": {
            title: "Tdata → Session",
            summary: "批量将 Telegram Desktop 文件夹转换为可直接在账号池中使用的 session 文件。",
          },
          "session-to-tdata": {
            title: "Session → Tdata",
            summary: "反向转换 — 将 session 还原为 Telegram Desktop 使用的文件夹格式。",
          },
          "open-session-folder": {
            title: "打开账号会话文件夹",
            summary: "在账号表格中一键在资源管理器中打开该账号 session 文件所在的文件夹。",
          },
        },
      },
      "auto-registration": {
        title: "自动注册",
        articles: {
          "hero-sms": {
            title: "Hero SMS",
            summary: "购买号码并通过 Hero SMS 服务商自动注册新账号，包括直接在应用内接收 2FA 验证码。",
          },
          smspool: {
            title: "SMSpool",
            summary: "通过 SMSpool 服务商实现相同的注册流程 — 价格和号码可用性模式有所不同。",
          },
          grizzlysms: {
            title: "GrizzlySMS",
            summary: "通过 GrizzlySMS 服务商实现相同的注册流程。",
          },
          datamoll: {
            title: "Datamoll",
            summary: "从 Datamoll 交易市场直接购入成品账号，为账号池补充库存 — 无需手动完成注册。",
          },
        },
      },
      audience: {
        title: "受众采集",
        articles: {
          "auto-strategy": {
            title: "智能自动策略",
            summary: "为每个群组或频道自动组合多种采集来源，而不是依赖单一来源（可能无法显示全部成员）。",
          },
          "audience-filters": {
            title: "受众筛选",
            summary: "在采集阶段即可按性别、活跃度、是否有头像、Premium 状态筛选，并排除机器人。",
          },
          "export-results": {
            title: "导出结果",
            summary: "每次采集结果单独保存 — 分别导出为 Excel、SQLite 和可读文本列表，并附带采集数量与对象的统计报告。",
          },
        },
      },
      sending: {
        title: "群发",
        articles: {
          "send-by-id": {
            title: "按 ID 群发",
            summary: "按 Telegram ID 或用户名列表发送文本、媒体和转发内容，支持定时发送，出现封号迹象时自动停止。",
          },
          "send-by-numbers": {
            title: "按号码群发",
            summary: "同一套群发引擎，只是收件人以电话号码列表指定。",
          },
          "text-randomizer": {
            title: "文本随机化",
            summary: "按模板对群发文本进行去重处理，避免收件人看到一字不差的相同消息。",
          },
        },
      },
      invite: {
        title: "邀请",
        articles: {
          "invite-by-number": {
            title: "按号码邀请",
            summary: "通过关联的发送账号，将受众（按 ID、用户名或采集结果导出）批量邀请进您的群组和频道。",
          },
        },
      },
      proxy: {
        title: "代理",
        articles: {
          "proxy-manager": {
            title: "代理管理",
            summary: "HTTP/SOCKS5 代理列表存储中心：批量添加、存活检测，一键清理失效代理。",
          },
          "proxy-pool-checker": {
            title: "代理池检测",
            summary: "通过代理发起请求并统计唯一出口 IP 数量，以判断服务商是否真的在轮换 IP。",
          },
        },
      },
    },
  },
  footer: {
    tagline: "面向 Windows 的 Telegram 账号矩阵管理工具。",
    navHeading: "导航",
    socialHeading: "社交媒体",
    docsHeading: "文档",
    social: { channel: "Telegram 频道", support: "技术支持" },
    docs: { privacy: "隐私政策", terms: "使用条款", offer: "公开要约" },
    copyright: "© 2026 Telegram Andromeda",
    disclaimer: "与 Telegram Messenger Inc. 无关联。",
  },
  cookieConsent: {
    dialogLabel: "Cookie 提示",
    message: "我们使用 Cookie 来改善网站体验。继续使用本网站即表示您同意使用 Cookie。",
    accept: "知道了",
  },
  contactBubble: {
    dialogLabel: "联系我们",
    title: "有疑问？",
    telegram: "通过 Telegram 联系我们",
    email: "发送邮件",
    open: "联系我们",
    close: "关闭联系窗口",
  },
  scrollToTop: {
    label: "返回顶部",
  },
};
