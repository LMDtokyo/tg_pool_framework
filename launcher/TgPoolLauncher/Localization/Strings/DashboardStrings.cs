namespace TgPoolLauncher.Localization.Strings;

internal static class DashboardStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Dashboard.UnproxiedWarningSuffix",
            " аккаунтов подключаются напрямую через IP этого компьютера, без прокси — риск разом забанить весь пул. Настройте им прокси на вкладке «Прокси».",
            " accounts connect directly through this computer's own IP, with no proxy — risking a ban cascade across the whole pool. Assign them a proxy on the Proxy tab.",
            " 个账号未使用代理，直接通过本机 IP 连接 — 存在整个账号池被连带封禁的风险。请在“代理”页面为它们配置代理。");
        table.Add("Dashboard.LiveFeed", "Лента событий", "Live feed", "事件流");
        table.Add("Dashboard.Connected", "Подключено", "Connected", "已连接");
        table.Add("Dashboard.Disconnected", "Отключено", "Disconnected", "未连接");
        table.Add("Dashboard.ColPhone", "Телефон", "Phone", "电话");
        table.Add("Dashboard.ColStatus", "Статус", "Status", "状态");
        table.Add("Dashboard.ColDetail", "Детали", "Details", "详情");

        table.Add("Dashboard.HeroCaption", "Материалы появятся здесь", "Content will appear here", "内容即将显示在此处");
        table.Add("Dashboard.QuickLinksHeader", "НЕОБХОДИМЫЕ ПРОГРАММЫ", "NECESSARY PROGRAMS", "必备软件");
        table.Add("Dashboard.NewsHeader", "НОВОСТИ И ГАЙДЫ", "NEWS & GUIDES", "新闻与指南");
        table.Add("Dashboard.ComingSoon", "Скоро", "Soon", "即将推出");
        table.Add("Dashboard.DownloadTooltip", "Скачать / установить", "Download / install", "下载／安装");

        table.Add("Dashboard.ToolChecking", "Проверка обновлений...", "Checking for updates...", "正在检查更新...");
        table.Add("Dashboard.ToolCheckFailed", "Не удалось проверить — нажмите, чтобы повторить",
            "Could not check — click to retry", "检查失败——点击重试");
        table.Add("Dashboard.ToolDownloadFailed", "Ошибка загрузки — нажмите, чтобы повторить",
            "Download failed — click to retry", "下载失败——点击重试");
        table.Add("Dashboard.ToolReadyToInstall", "Загружено — нажмите, чтобы установить",
            "Downloaded — click to install", "已下载——点击安装");
        table.Add("Dashboard.ToolUpToDateFormat", "Установлено (v{0}) — нажмите, чтобы запустить установщик",
            "Installed (v{0}) — click to run the installer", "已安装（v{0}）——点击运行安装程序");
        table.Add("Dashboard.ToolAvailableFormat", "Доступно (v{0})", "Available (v{0})", "可下载（v{0}）");
        table.Add("Dashboard.ToolUpdateAvailableFormat", "Обновление v{1} (у вас v{0})",
            "Update v{1} available (you have v{0})", "有更新 v{1}（当前 v{0}）");

        table.Add("Dashboard.ToolNppDescription",
            "Удобный текстовый редактор — пригодится для просмотра отчётов и списков (.txt) после парсинга",
            "A handy text editor — useful for viewing parsing reports and audience lists (.txt)",
            "便捷的文本编辑器——用于查看解析后的报告和名单（.txt）");
        table.Add("Dashboard.ToolDbBrowserDescription",
            "Просмотр и редактирование SQLite-баз — открывайте database.db, который сохраняется после каждого парсинга",
            "Browse and edit SQLite databases — open the database.db saved after every parsing run",
            "浏览和编辑 SQLite 数据库——打开每次解析后保存的 database.db");
        table.Add("Dashboard.ToolLetosDescription",
            "Ещё один менеджер SQLite-баз (ранее SQLiteStudio) — альтернатива DB Browser для тех же .db файлов",
            "Another SQLite database manager (formerly SQLiteStudio) — an alternative to DB Browser for the same .db files",
            "另一款 SQLite 数据库管理工具（原 SQLiteStudio）——用于同样的 .db 文件，是 DB Browser 的替代品");
    }
}
