namespace TgPoolLauncher.Localization.Strings;

internal static class AccountsStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Status.Alive", "Без ограничений", "Unrestricted", "无限制");
        table.Add("Status.Banned", "Забанен", "Banned", "已封禁");
        table.Add("Status.Unauthorized", "Не авторизован", "Unauthorized", "未授权");
        table.Add("Status.Spamblock", "Спамблок", "Spam block", "垃圾邮件限制");
        table.Add("Status.Frozen", "Заморожен", "Frozen", "已冻结");
        table.Add("Status.Flood", "Флуд-лимит", "Flood limit", "洪水限制");
        table.Add("Status.ProxyDead", "Прокси недоступен", "Proxy unavailable", "代理不可用");
        table.Add("Status.Unknown", "Неизвестно", "Unknown", "未知");

        table.Add("Time.DaysSuffix", "дн", "d", "天");
        table.Add("Time.MonthsSuffix", "мес", "mo", "个月");
        table.Add("Time.YearsSuffix", "г", "y", "年");
        table.Add("Time.Today", "Сегодня", "Today", "今天");
        table.Add("Time.Yesterday", "Вчера", "Yesterday", "昨天");

        table.Add("Accounts.FilterStatusAll", "Статус", "Status", "状态");
        table.Add("Accounts.FilterRoleAll", "Роль", "Role", "角色");
        table.Add("Accounts.FilterFolderAll", "Папка", "Folder", "文件夹");
        table.Add("Accounts.FilterGeoAll", "Гео", "Geo", "地区");
        table.Add("Accounts.MoreFiltersTooltip", "Ещё фильтры (скоро)", "More filters (soon)", "更多筛选（即将推出）");
        table.Add("Accounts.RefreshTooltip",
            "Перечитать список — подхватит аккаунты, добавленные в Data\\Accounts",
            "Reload the list — picks up accounts added to Data\\Accounts",
            "重新读取列表——会包含添加到 Data\\Accounts 的账户");
        table.Add("Accounts.RecheckPool", "Перепроверить пул", "Recheck pool", "重新检测账户池");

        table.Add("Accounts.ColAccount", "Аккаунт", "Account", "账户");
        table.Add("Accounts.ColGeo", "Гео", "Geo", "地区");
        table.Add("Accounts.ColStatus", "Статус", "Status", "状态");
        table.Add("Accounts.ColTracked", "Отслежка", "Tracked", "追踪时长");
        table.Add("Accounts.ColRole", "Роль", "Role", "角色");
        table.Add("Accounts.ColProxy", "Прокси", "Proxy", "代理");
        table.Add("Accounts.ColLastUsed", "Использован", "Last used", "最近使用");
        table.Add("Accounts.ColName", "Имя", "Name", "姓名");
        table.Add("Accounts.ColOther", "Разное", "Other", "其他");

        table.Add("Accounts.ProxyDirect", "Прямой", "Direct", "直连");
        table.Add("Accounts.ProxyConfigured", "Прокси", "Proxy", "代理");
        table.Add("Accounts.ProxyCheckedActive", "Прокси активен", "Proxy active", "代理可用");
        table.Add("Accounts.ProxyCheckedDead", "Прокси недоступен", "Proxy unavailable", "代理不可用");
        table.Add("Accounts.ProxyDirectTooltip", "Для этого аккаунта прокси не настроен", "No proxy is configured for this account", "此账户未配置代理");

        table.Add("Accounts.TooltipFolder", "Папка", "Folder", "文件夹");
        table.Add("Accounts.TooltipUsername", "Username", "Username", "用户名");
        table.Add("Accounts.TooltipInfo", "Инфо", "Info", "信息");
        table.Add("Accounts.TooltipMonitor", "Монитор", "Monitor", "监控");

        table.Add("Accounts.StatusCountFormat", "{0} аккаунт(ов)", "{0} account(s)", "共 {0} 个账户");
        table.Add("Accounts.LoadErrorFormat", "Ошибка загрузки: {0}", "Load error: {0}", "加载错误：{0}");
        table.Add("Accounts.RecheckResultFormat",
            "Проверено: {0}, живых: {1}, бан: {2}, не авторизован: {3}",
            "Checked: {0}, alive: {1}, banned: {2}, unauthorized: {3}",
            "已检测：{0}，正常：{1}，封禁：{2}，未授权：{3}");
        table.Add("Accounts.RecheckErrorFormat", "Ошибка проверки: {0}", "Check error: {0}", "检测错误：{0}");
    }
}
