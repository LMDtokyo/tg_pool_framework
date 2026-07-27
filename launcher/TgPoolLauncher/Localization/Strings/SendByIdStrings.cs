namespace TgPoolLauncher.Localization.Strings;

internal static class SendByIdStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("SendById.WorkWithTextHeader", "РАБОТА С ТЕКСТОМ", "WORK WITH TEXT", "文本编辑");
        table.Add("SendById.ClearMessageTooltip", "Очистить сообщение", "Clear message", "清除消息");
        table.Add("SendById.BoldTooltip", "Жирный", "Bold", "粗体");
        table.Add("SendById.ItalicTooltip", "Курсив", "Italic", "斜体");
        table.Add("SendById.CodeTooltip", "Код", "Code", "代码");
        table.Add("SendById.AddLinkTooltip", "Добавить ссылку", "Add link", "添加链接");
        table.Add("SendById.RepostFromChannelTooltip", "Репост из канала", "Repost from channel", "从频道转发");
        table.Add("SendById.AttachFileTooltip", "Прикрепить файл", "Attach file", "附加文件");
        table.Add("SendById.RepostViaPostbotTooltip", "Репост через Postbot", "Repost via Postbot", "通过 Postbot 转发");
        table.Add("SendById.TextRandomizerTooltip", "Рандомизатор текста", "Text randomizer", "文本随机器");
        table.Add("SendById.InsertRecipientUsernameTooltip", "Вставить имя пользователя получателя", "Insert recipient username", "插入收件人用户名");

        table.Add("SendById.SettingsHeader", "НАСТРОЙКИ", "SETTINGS", "设置");
        table.Add("SendById.ResetTooltip", "Сбросить настройки", "Reset settings", "重置设置");
        table.Add("SendById.ResetButton", "Сбросить", "Reset", "重置");

        table.Add("SendById.DatabaseLabel", "База данных", "Database", "数据库");
        table.Add("SendById.DatabaseTooltip", "База данных Telegram ID пользователей", "Database of Telegram user IDs", "Telegram 用户 ID 数据库");
        table.Add("SendById.ChooseDatabaseTooltip", "Выбрать базу данных", "Choose database", "选择数据库");
        table.Add("SendById.ParsedDatabaseHintFormat", "Свежая база из парсинга: {0} польз. — {1}",
            "Freshly parsed database: {0} users — {1}", "刚采集的数据库：{0} 位用户 — {1}");
        table.Add("SendById.UseParsedDatabaseButton", "Использовать", "Use it", "使用");

        table.Add("SendById.SmsPerAccountLabel", "SMS на аккаунт", "SMS per account", "每账号短信数");
        table.Add("SendById.DelayLabel", "Задержка", "Delay", "延迟");
        table.Add("SendById.FloodWaitLabel", "Максимальное ожидание (FloodWait)", "Maximum timeout (FloodWait)", "最大超时（FloodWait）");

        table.Add("SendById.SelectAccountsLabel", "Выбрать аккаунты", "Select Accounts", "选择账号");
        table.Add("SendById.SelectAccountsButton", "Выбрать аккаунты", "Select Accounts", "选择账号");

        table.Add("SendById.DeleteDialogLabel", "Удалять диалог после отправки", "Delete dialog after messaging", "发送后删除对话");
        table.Add("SendById.PreviewLinksLabel", "Предпросмотр ссылок", "Preview links", "链接预览");
        table.Add("SendById.SilentModeLabel", "Тихий режим", "Silent mode", "静默模式");
        table.Add("SendById.AutoRepostLabel", "Авто-репост", "Auto repost", "自动转发");
        table.Add("SendById.LeaveDonorGroupsLabel", "Выходить из групп-доноров", "Leave donor groups", "退出供体组");
        table.Add("SendById.PinMessageLabel", "Закрепить сообщение в чате", "Pin message in chat", "在聊天中置顶消息");

        table.Add("SendById.SendingFilesHeader", "ОТПРАВКА ФАЙЛОВ", "SENDING FILES", "发送文件");
        table.Add("SendById.VideoCircleLabel", "Отправить видео кружком (*.mp4)", "Send video in a circle (*.mp4)", "以圆形视频发送（*.mp4）");
        table.Add("SendById.SelfDestructLabel", "Файл самоуничтожится через 60 секунд", "File self-destruct in 60 seconds", "文件60秒后自动销毁");

        table.Add("SendById.AdditionalSettingsHeader", "ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ", "ADDITIONAL SETTINGS", "附加设置");
        table.Add("SendById.SendingByTimeLabel", "Отправка по времени", "Sending by time", "定时发送");
        table.Add("SendById.ScheduleAtTooltip", "Местное время: yyyy-MM-dd HH:mm", "Local time: yyyy-MM-dd HH:mm", "本地时间：yyyy-MM-dd HH:mm");

        table.Add("SendById.StreamsControlLabel", "Управление потоками", "Streams control", "流控制");
        table.Add("SendById.StreamsTooltip", "Количество одновременно работающих аккаунтов", "Number of accounts working simultaneously", "同时工作的账号数量");

        table.Add("SendById.AutoStopLabel", "Авто-стоп", "Auto stop", "自动停止");
        table.Add("SendById.RunControlLabel", "Управление запуском", "Run control", "运行控制");
        table.Add("SendById.AutoStopBanLabel", "БАН", "BAN", "封禁");
        table.Add("SendById.AutoStopBanTooltip", "Остановить после стольких заблокированных аккаунтов", "Stop after this many banned accounts", "封禁账号达到此数量后停止");
        table.Add("SendById.AutoStopSpamBlockTooltip", "Остановить после стольких аккаунтов со SpamBlock", "Stop after this many SpamBlock accounts", "SpamBlock 账号达到此数量后停止");
        table.Add("SendById.AutoStopFloodWaitTooltip", "Остановить после стольких событий FloodWait", "Stop after this many FloodWait events", "FloodWait 事件达到此数量后停止");
        table.Add("SendById.RepeatHoursLabel", "Часов повтора", "Repeat hours", "重复小时数");
        table.Add("SendById.RepeatHoursTooltip", "Интервал повтора в часах", "Repeat interval in hours", "重复间隔（小时）");

        table.Add("SendById.MessageViewHeader", "ПРОСМОТР СООБЩЕНИЯ", "MESSAGE VIEW", "消息预览");
        table.Add("SendById.ProgramActionsHeader", "ДЕЙСТВИЯ ПРОГРАММЫ", "PROGRAM ACTIONS", "程序操作");

        table.Add("SendById.LogColTime", "Время", "Time", "时间");
        table.Add("SendById.LogColAccount", "Аккаунт", "Account", "账号");
        table.Add("SendById.LogColMessage", "Сообщение", "Message", "消息");
        table.Add("SendById.NoResultsYet", "Результатов ещё нет", "No results yet", "暂无结果");

        table.Add("SendById.ModalCloseTooltip", "Закрыть", "Close", "关闭");
        table.Add("SendById.ChooseLocalFileButton", "Выбрать локальный файл", "Choose local file", "选择本地文件");
        table.Add("SendById.BotUsernameLabel", "Имя пользователя бота", "Bot username", "机器人用户名");
        table.Add("SendById.PostIdsLabel", "ID поста(ов), по одному в строке", "Post ID(s), one per line", "帖子 ID，每行一个");
        table.Add("SendById.ModalApplyButton", "Применить", "Apply", "应用");
    }
}
