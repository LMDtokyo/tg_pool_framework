namespace TgPoolLauncher.Localization.Strings;

internal static class DashboardStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Dashboard.LiveFeed", "Лента событий", "Live feed", "事件流");
        table.Add("Dashboard.Connected", "подключено", "connected", "已连接");
        table.Add("Dashboard.Disconnected", "отключено", "disconnected", "未连接");
        table.Add("Dashboard.ColPhone", "Телефон", "Phone", "电话");
        table.Add("Dashboard.ColStatus", "Статус", "Status", "状态");
        table.Add("Dashboard.ColDetail", "Детали", "Details", "详情");
    }
}
