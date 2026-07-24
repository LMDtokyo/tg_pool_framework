namespace TgPoolLauncher.Localization.Strings;

internal static class DashboardStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Dashboard.LiveFeed", "Лента событий", "Live feed", "事件流");
        table.Add("Dashboard.Connected", "подключено", "connected", "已连接");
        table.Add("Dashboard.Disconnected", "отключено", "disconnected", "未连接");
        table.Add("Dashboard.Total", "Всего", "Total", "总计");
        table.Add("Dashboard.Sent", "Отправлено", "Sent", "已发送");
        table.Add("Dashboard.Failed", "Ошибок", "Errors", "错误");
        table.Add("Dashboard.Status", "Статус", "Status", "状态");
        table.Add("Dashboard.NotRunning", "Не запущена", "Not running", "未运行");
        table.Add("Dashboard.Running", "Идёт рассылка", "Campaign running", "群发进行中");
        table.Add("Dashboard.ColPhone", "Телефон", "Phone", "电话");
        table.Add("Dashboard.ColStatus", "Статус", "Status", "状态");
        table.Add("Dashboard.ColDetail", "Детали", "Details", "详情");
    }
}
