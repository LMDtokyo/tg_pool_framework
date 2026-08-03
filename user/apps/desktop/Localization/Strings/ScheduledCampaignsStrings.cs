namespace TgPoolLauncher.Localization.Strings;

internal static class ScheduledCampaignsStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("ScheduledCampaigns.NewSchedule", "Новое расписание", "New schedule", "新建计划");
        table.Add("ScheduledCampaigns.NameLabel", "Название", "Name", "名称");
        table.Add("ScheduledCampaigns.CampaignTypeLabel", "Тип рассылки", "Campaign type", "群发类型");
        table.Add("ScheduledCampaigns.SendByIdOption", "По ID", "By ID", "按 ID");
        table.Add("ScheduledCampaigns.SendByNumbersOption", "По номерам", "By phone number", "按号码");
        table.Add("ScheduledCampaigns.DatabasePathLabel", "База данных", "Database", "数据库");
        table.Add("ScheduledCampaigns.PhoneNumbersLabel", "Номера телефонов", "Phone numbers", "电话号码");
        table.Add("ScheduledCampaigns.MessageLabel", "Текст сообщения", "Message text", "消息文本");
        table.Add("ScheduledCampaigns.ScheduleHeader", "РАСПИСАНИЕ", "SCHEDULE", "计划");
        table.Add("ScheduledCampaigns.StartDateLabel", "Дата запуска", "Start date", "开始日期");
        table.Add("ScheduledCampaigns.StartTimeLabel", "Время (ЧЧ:ММ)", "Time (HH:mm)", "时间（HH:mm）");
        table.Add("ScheduledCampaigns.RepeatIntervalLabel", "Повтор, ч (необязательно)", "Repeat every, h (optional)", "重复间隔，小时（可选）");
        table.Add("ScheduledCampaigns.RepeatIntervalTooltip",
            "Оставьте пустым для одноразовой отправки", "Leave empty for a one-time send", "留空表示仅发送一次");
        table.Add("ScheduledCampaigns.MaxOccurrencesLabel", "Максимум повторов", "Max occurrences", "最大重复次数");
        table.Add("ScheduledCampaigns.MaxOccurrencesTooltip",
            "Оставьте пустым для повтора без ограничений", "Leave empty to repeat indefinitely", "留空表示无限重复");
        table.Add("ScheduledCampaigns.CreateButton", "Создать расписание", "Create schedule", "创建计划");

        table.Add("ScheduledCampaigns.ListHeader", "ЗАПЛАНИРОВАННЫЕ КАМПАНИИ", "SCHEDULED CAMPAIGNS", "已计划的群发");
        table.Add("ScheduledCampaigns.EmptyListMessage", "Пока нет запланированных кампаний", "No scheduled campaigns yet", "暂无已计划的群发");
        table.Add("ScheduledCampaigns.DisabledBadge", "ОТКЛЮЧЕНО", "DISABLED", "已停用");
        table.Add("ScheduledCampaigns.NextRunLabel", "Следующий запуск", "Next run", "下次运行");
        table.Add("ScheduledCampaigns.RepeatLabel", "Повтор", "Repeat", "重复");
        table.Add("ScheduledCampaigns.HoursSuffix", "ч", "h", "小时");
        table.Add("ScheduledCampaigns.LastRunLabel", "Последний запуск", "Last run", "上次运行");

        table.Add("ScheduledCampaigns.ChooseDatabaseTitle", "Выбрать базу данных", "Choose database", "选择数据库");
        table.Add("ScheduledCampaigns.ChooseDatabaseFilter",
            "Файлы аудитории (*.txt;*.csv;*.json;*.xlsx;*.xls)|*.txt;*.csv;*.json;*.xlsx;*.xls|Все файлы|*.*",
            "Audience files (*.txt;*.csv;*.json;*.xlsx;*.xls)|*.txt;*.csv;*.json;*.xlsx;*.xls|All files|*.*",
            "受众文件 (*.txt;*.csv;*.json;*.xlsx;*.xls)|*.txt;*.csv;*.json;*.xlsx;*.xls|所有文件|*.*");
        table.Add("ScheduledCampaigns.InvalidTimeError",
            "Введите время в формате ЧЧ:ММ", "Enter the time as HH:mm", "请输入格式为 HH:mm 的时间");
        table.Add("ScheduledCampaigns.InvalidRepeatError",
            "Интервал повтора должен быть положительным числом часов", "Repeat interval must be a positive number of hours", "重复间隔必须是正数（小时）");
        table.Add("ScheduledCampaigns.InvalidMaxOccurrencesError",
            "Максимум повторов должен быть числом не меньше 1", "Max occurrences must be a number of at least 1", "最大重复次数必须是不小于 1 的数字");
    }
}
