namespace TgPoolLauncher.Localization.Strings;

internal static class DashboardStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Dashboard.LiveFeed", "Лента событий", "Live feed", "事件流");
        table.Add("Dashboard.Connected", "Подключено", "Connected", "已连接");
        table.Add("Dashboard.Disconnected", "Отключено", "Disconnected", "未连接");
        table.Add("Dashboard.ColPhone", "Телефон", "Phone", "电话");
        table.Add("Dashboard.ColStatus", "Статус", "Status", "状态");
        table.Add("Dashboard.ColDetail", "Детали", "Details", "详情");

        table.Add("Dashboard.HeroCaption", "Материалы появятся здесь", "Content will appear here", "内容即将显示在此处");
        table.Add("Dashboard.QuickLinksHeader", "ПОЛЕЗНЫЕ МАТЕРИАЛЫ", "USEFUL MATERIALS", "常用资料");
        table.Add("Dashboard.NewsHeader", "НОВОСТИ И ГАЙДЫ", "NEWS & GUIDES", "新闻与指南");
        table.Add("Dashboard.ComingSoon", "Скоро", "Soon", "即将推出");
    }
}
