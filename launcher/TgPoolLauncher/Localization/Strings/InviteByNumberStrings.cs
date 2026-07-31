namespace TgPoolLauncher.Localization.Strings;

internal static class InviteByNumberStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("InviteByNumber.ResetSettingsTooltip", "Сбросить настройки", "Reset settings", "重置设置");

        table.Add("InviteByNumber.UseBaseDataLabel", "Использовать базовые данные", "Use base data", "使用基础数据");
        table.Add("InviteByNumber.UseBaseDataNoTooltip", "Не использовать базовые данные", "Do not use base data", "不使用基础数据");
        table.Add("InviteByNumber.LeaveMainGroupLabel", "Выйти из основной группы", "Leave the main group", "退出主群组");

        table.Add("InviteByNumber.DatabaseLabel", "База данных", "Database", "数据库");
        table.Add("InviteByNumber.DatabasePathPlaceholder", "Путь к файлу базы данных", "Path to the database file", "数据库文件路径");
        table.Add("InviteByNumber.ChooseDatabaseFileTooltip", "Выбрать xlsx-файл базы данных", "Choose xlsx database file", "选择 xlsx 数据库文件");

        table.Add("InviteByNumber.GroupsLabel", "Группы", "Groups", "群组");
        table.Add("InviteByNumber.RefreshGroupsTooltip", "Обновить аккаунты и присоединённые группы", "Refresh accounts and joined groups", "刷新账号和已加入的群组");
        table.Add("InviteByNumber.GroupsPlaceholder", "Номер\nГруппа1\nГруппа2", "Number\nGroup1\nGroup2", "编号\n群组1\n群组2");

        table.Add("InviteByNumber.MaxPerAccountLabel", "Всего пользователей на аккаунт", "Total users per account", "每个账号总用户数");
        table.Add("InviteByNumber.MaxPerRequestLabel", "Всего пользователей на запрос", "Total users per request", "每次请求总用户数");
        table.Add("InviteByNumber.MinOneUserNote", "мин. 1 пользователь", "min 1 user", "最少 1 个用户");
        table.Add("InviteByNumber.MaxOneUserNote", "макс. 1 пользователь", "max 1 user", "最多 1 个用户");

        table.Add("InviteByNumber.DelayLabel", "Задержка", "Delay", "延迟");
        table.Add("InviteByNumber.MaxFloodWaitLabel", "Максимальное ожидание (FloodWait)", "Maximum timeout (FloodWait)", "最大超时（FloodWait）");

        table.Add("InviteByNumber.RequireProxyLabel", "Требовать прокси", "Require proxy", "需要代理");
        table.Add("InviteByNumber.RequireProxyTooltip",
            "Запретить запуск, если у выбранного отправителя нет прокси или несколько отправителей используют один и тот же прокси.",
            "Refuse to start if a selected sender has no proxy, or if senders share one proxy.",
            "如果所选发送账号没有代理，或多个发送账号共用同一个代理，则拒绝启动。");

        table.Add("InviteByNumber.SelectAccountsLabel", "Выбрать аккаунты", "Select Accounts", "选择账号");
        table.Add("InviteByNumber.SelectAccountsButton", "Выбрать аккаунты", "Select Accounts", "选择账号");

        table.Add("InviteByNumber.StreamsControlLabel", "Управление потоками", "Streams Control", "流控制");
        table.Add("InviteByNumber.AutoStopLabel", "Авто-стоп", "Auto stop", "自动停止");
        table.Add("InviteByNumber.RequestProfileFieldsLabel", "Запрашивать имя, фамилию, био", "Request First name, Last name, Bio", "请求名字、姓氏、简介");

        table.Add("InviteByNumber.ImportantInfoHeader", "ВАЖНАЯ ИНФОРМАЦИЯ !", "IMPORTANT INFORMATION !", "重要信息！");
        table.Add("InviteByNumber.ImportantInfoText",
            "Используйте столбец ID из экспортов парсинга (Telegram user id), а не PhoneNumber. Держите лимиты умеренными. Отправляющая сессия должна уже знать получателя (общая группа/история диалога) или получатель должен иметь публичный @username, иначе Telethon не сможет найти этот объект.",
            "Use the ID column from parse exports (Telegram user id), not PhoneNumber. Keep limits moderate. The sender session must already know the recipient (same group/dialog history) or have a public @username, otherwise Telethon cannot resolve the entity.",
            "请使用解析导出中的 ID 列（Telegram 用户 ID），而不是 PhoneNumber 列。请保持适度的限制。发送账号的会话必须已经认识该接收者（共同群组/对话历史），或者接收者拥有公开的 @username，否则 Telethon 无法解析该对象。");

        table.Add("InviteByNumber.ReceiverIdsHeaderInitial", "ID ПОЛУЧАТЕЛЕЙ : 0", "RECEIVER IDs : 0", "接收方 ID：0");
        table.Add("InviteByNumber.ReceiverIdsHeaderFormat", "ID ПОЛУЧАТЕЛЕЙ : {0}", "RECEIVER IDs : {0}", "接收方 ID：{0}");
        table.Add("InviteByNumber.DeleteReceiverIdsTooltip", "Удалить ID получателей", "Delete receiver IDs", "删除接收方 ID");
        table.Add("InviteByNumber.ReceiverIdsPlaceholder",
            "Список Telegram ID получателей (столбец ID из экспорта), по одному в строке:\n8535286786\n8820638155\n@username\n\n" +
            "Загрузите xlsx-экспорт парсинга (столбец ID) через «Использовать базовые данные» или вставьте ID сюда.\n" +
            "Вставьте ссылки-приглашения https://t.me/... под каждым аккаунтом-отправителем в разделе «Группы», затем нажмите «Запустить».",
            "List of Telegram receiver IDs (export ID column), one per line:\n8535286786\n8820638155\n@username\n\n" +
            "Load a parse export xlsx (ID column) via Use base data, or paste IDs here.\n" +
            "Paste https://t.me/... invite links under each sender account in Groups, then press Run.",
            "Telegram 接收方 ID 列表（导出的 ID 列），每行一个：\n8535286786\n8820638155\n@username\n\n" +
            "通过“使用基础数据”加载解析导出的 xlsx 文件（ID 列），或在此粘贴 ID。\n" +
            "在“群组”中每个发送账号下粘贴 https://t.me/... 邀请链接，然后点击运行。");

        table.Add("InviteByNumber.OpenResultsFolderTooltip", "Открыть папку результатов", "Open results folder", "打开结果文件夹");

        table.Add("InviteByNumber.ProgramActionsHeader", "ДЕЙСТВИЯ ПРОГРАММЫ", "PROGRAM ACTIONS", "程序操作");
        table.Add("InviteByNumber.BuildInviteActionsTooltip", "Сформировать действия приглашения", "Build invite actions", "生成邀请操作");
        table.Add("InviteByNumber.StopInviteRequestsTooltip", "Остановить запросы на приглашение", "Stop invite requests", "停止邀请请求");
        table.Add("InviteByNumber.ClearProgramActionsTooltip", "Остановить и удалить все элементы", "Stop and remove all items", "停止并删除所有项目");

        table.Add("InviteByNumber.LogColTime", "Время", "Time", "时间");
        table.Add("InviteByNumber.LogColAccount", "Аккаунт", "Account", "账号");
        table.Add("InviteByNumber.LogColState", "Статус", "State", "状态");
        table.Add("InviteByNumber.LogColMessage", "Сообщение", "Message", "消息");

        table.Add("InviteByNumber.SelectDatabaseDialogTitle", "Выбрать базу данных получателей", "Select receiver ID database", "选择接收方 ID 数据库");
        table.Add("InviteByNumber.ExcelWorkbookFilter", "Книга Excel (*.xlsx)|*.xlsx", "Excel workbook (*.xlsx)|*.xlsx", "Excel 工作簿 (*.xlsx)|*.xlsx");

        table.Add("InviteByNumber.JobLabel", "Приглашение по номеру", "Invite by number", "按号码邀请");
        table.Add("InviteByNumber.BaseDataJobLabel", "Базовые данные", "Base data", "基础数据");

        table.Add("InviteByNumber.NoBaseDataMessage",
            "Загрузите xlsx-экспорт парсинга с Telegram ID в столбце ID или вставьте ID справа.",
            "Load a parse export xlsx with Telegram IDs in the ID column, or paste IDs on the right.",
            "请加载解析导出的 xlsx 文件（ID 列包含 Telegram ID），或在右侧粘贴 ID。");
        table.Add("InviteByNumber.NoManualIdsMessage",
            "Вставьте Telegram ID получателей справа перед запуском.",
            "Paste receiver Telegram IDs on the right before running.",
            "请在开始前于右侧粘贴接收方 Telegram ID。");
        table.Add("InviteByNumber.NoInviteLinksMessage",
            "Введите хотя бы одну ссылку-приглашение https://t.me/... под сохранённым аккаунтом в разделе «Группы».",
            "Enter at least one https://t.me/... invite link under a saved account in Groups.",
            "请在“群组”中的某个已保存账号下输入至少一个 https://t.me/... 邀请链接。");
        table.Add("InviteByNumber.SenderMappingFailedMessage",
            "Не удалось сопоставить метку отправителя с сохранённым номером аккаунта.",
            "Could not map sender label to a saved account phone.",
            "无法将发送账号标签映射到已保存的账号电话号码。");

        table.Add("InviteByNumber.StartedJobFormat", "Запущена задача {0}", "Started job {0}", "已启动任务 {0}");
        table.Add("InviteByNumber.RequestsStoppedMessage", "Запросы на приглашение остановлены.", "Invite requests stopped.", "邀请请求已停止。");
        table.Add("InviteByNumber.JobFailedToStartMessage", "Не удалось запустить задачу.", "Job failed to start.", "任务启动失败。");
        table.Add("InviteByNumber.StopRequestedMessage", "Запрошена остановка.", "Stop requested.", "已请求停止。");
        table.Add("InviteByNumber.StopFailedFormat", "Не удалось остановить: {0}", "Stop failed: {0}", "停止失败：{0}");
        table.Add("InviteByNumber.FinishedSummaryFormat", "Завершено: отправлено {0}, ошибок {1}.", "Finished: sent {0}, failed {1}.", "已完成：已发送 {0}，失败 {1}。");
        table.Add("InviteByNumber.FinishedErrorFormat", "Завершено с ошибкой: {0}", "Finished with error: {0}", "因错误结束：{0}");

        table.Add("InviteByNumber.NoIdsFoundFormat",
            "В столбце ID файла {0} не найдено Telegram ID",
            "No Telegram IDs found in the ID column of {0}",
            "在文件 {0} 的 ID 列中未找到 Telegram ID");
        table.Add("InviteByNumber.QueuedForFormat", "В очереди для {0} (ID {1})", "Queued for {0} (ID {1})", "已加入队列：{0}（ID {1}）");
        table.Add("InviteByNumber.ViaSenderFormat", "{0} через {1}", "{0} via {1}", "{0}，通过 {1}");
        table.Add("InviteByNumber.IdLabelFormat", "ID {0}", "ID {0}", "ID {0}");
        table.Add("InviteByNumber.AddedFromFileFormat", "Добавлено {0} из {1}", "Added {0} from {1}", "已从 {1} 添加 {0}");
    }
}
