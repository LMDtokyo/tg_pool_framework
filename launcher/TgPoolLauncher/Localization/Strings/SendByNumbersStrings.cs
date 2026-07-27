namespace TgPoolLauncher.Localization.Strings;

internal static class SendByNumbersStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("SendByNumbers.WorkWithTextHeader", "РАБОТА С ТЕКСТОМ", "WORK WITH TEXT", "文本编辑");
        table.Add("SendByNumbers.ClearMessageTooltip", "Очистить сообщение", "Clear message", "清除消息");
        table.Add("SendByNumbers.BoldTooltip", "Жирный", "Bold", "粗体");
        table.Add("SendByNumbers.ItalicTooltip", "Курсив", "Italic", "斜体");
        table.Add("SendByNumbers.CodeTooltip", "Код", "Code", "代码");
        table.Add("SendByNumbers.AddLinkTooltip", "Добавить ссылку", "Add link", "添加链接");
        table.Add("SendByNumbers.RepostFromChannelTooltip", "Репост из канала", "Repost from channel", "从频道转发");
        table.Add("SendByNumbers.AttachFileTooltip", "Прикрепить файл", "Attach file", "附加文件");
        table.Add("SendByNumbers.RepostViaPostbotTooltip", "Репост через Postbot", "Repost via Postbot", "通过 Postbot 转发");
        table.Add("SendByNumbers.TextRandomizerTooltip", "Рандомизатор текста", "Text randomizer", "文本随机器");
        table.Add("SendByNumbers.InsertRecipientPhoneTooltip", "Вставить телефон получателя", "Insert recipient phone", "插入收件人电话");

        table.Add("SendByNumbers.SettingsHeader", "НАСТРОЙКИ", "SETTINGS", "设置");
        table.Add("SendByNumbers.ResetTooltip", "Сбросить настройки", "Reset settings", "重置设置");
        table.Add("SendByNumbers.ResetButton", "Сбросить", "Reset", "重置");

        table.Add("SendByNumbers.PhoneNumbersLabel", "Телефонные номера", "Phone numbers", "电话号码");
        table.Add("SendByNumbers.PhoneNumbersTooltip", "Введите номера телефонов через запятую, пробел или новую строку", "Enter phone numbers separated by commas, spaces, or new lines", "输入电话号码，用逗号、空格或换行分隔");
        table.Add("SendByNumbers.ImportPhoneNumbersTooltip", "Импортировать номера из текстового или CSV-файла", "Import phone numbers from a text or CSV file", "从文本或 CSV 文件导入电话号码");

        table.Add("SendByNumbers.SmsPerAccountLabel", "SMS на аккаунт", "SMS per account", "每账号短信数");
        table.Add("SendByNumbers.DelayLabel", "Задержка", "Delay", "延迟");
        table.Add("SendByNumbers.FloodWaitLabel", "Максимальное ожидание (FloodWait)", "Maximum timeout (FloodWait)", "最大超时（FloodWait）");

        table.Add("SendByNumbers.SelectAccountsLabel", "Выбрать аккаунты", "Select Accounts", "选择账号");
        table.Add("SendByNumbers.SelectAccountsButton", "Выбрать аккаунты", "Select Accounts", "选择账号");

        table.Add("SendByNumbers.DeleteDialogLabel", "Удалять диалог после отправки", "Delete dialog after messaging", "发送后删除对话");
        table.Add("SendByNumbers.PreviewLinksLabel", "Предпросмотр ссылок", "Preview links", "链接预览");
        table.Add("SendByNumbers.SilentModeLabel", "Тихий режим", "Silent mode", "静默模式");
        table.Add("SendByNumbers.AutoRepostLabel", "Авто-репост", "Auto repost", "自动转发");
        table.Add("SendByNumbers.RemoveImportedContactsLabel", "Удалять импортированные контакты", "Remove imported contacts", "删除导入的联系人");
        table.Add("SendByNumbers.PinMessageLabel", "Закрепить сообщение в чате", "Pin message in chat", "在聊天中置顶消息");

        table.Add("SendByNumbers.SendingFilesHeader", "ОТПРАВКА ФАЙЛОВ", "SENDING FILES", "发送文件");
        table.Add("SendByNumbers.VideoCircleLabel", "Отправить видео кружком (*.mp4)", "Send video in a circle (*.mp4)", "以圆形视频发送（*.mp4）");
        table.Add("SendByNumbers.SelfDestructLabel", "Файл самоуничтожится через 60 секунд", "File self-destruct in 60 seconds", "文件60秒后自动销毁");

        table.Add("SendByNumbers.AdditionalSettingsHeader", "ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ", "ADDITIONAL SETTINGS", "附加设置");
        table.Add("SendByNumbers.SendingByTimeLabel", "Отправка по времени", "Sending by time", "定时发送");
        table.Add("SendByNumbers.ScheduleAtTooltip", "Местное время: yyyy-MM-dd HH:mm", "Local time: yyyy-MM-dd HH:mm", "本地时间：yyyy-MM-dd HH:mm");

        table.Add("SendByNumbers.StreamsControlLabel", "Управление потоками", "Streams control", "流控制");
        table.Add("SendByNumbers.StreamsTooltip", "Количество одновременно работающих аккаунтов", "Number of accounts working simultaneously", "同时工作的账号数量");

        table.Add("SendByNumbers.AutoStopLabel", "Авто-стоп", "Auto stop", "自动停止");
        table.Add("SendByNumbers.RunControlLabel", "Управление запуском", "Run control", "运行控制");
        table.Add("SendByNumbers.AutoStopBanLabel", "БАН", "BAN", "封禁");
        table.Add("SendByNumbers.AutoStopBanTooltip", "Остановить после стольких заблокированных аккаунтов", "Stop after this many banned accounts", "封禁账号达到此数量后停止");
        table.Add("SendByNumbers.AutoStopSpamBlockTooltip", "Остановить после стольких аккаунтов со SpamBlock", "Stop after this many SpamBlock accounts", "SpamBlock 账号达到此数量后停止");
        table.Add("SendByNumbers.AutoStopFloodWaitTooltip", "Остановить после стольких событий FloodWait", "Stop after this many FloodWait events", "FloodWait 事件达到此数量后停止");
        table.Add("SendByNumbers.RepeatHoursLabel", "Часов повтора", "Repeat hours", "重复小时数");
        table.Add("SendByNumbers.RepeatHoursTooltip", "Интервал повтора в часах", "Repeat interval in hours", "重复间隔（小时）");

        table.Add("SendByNumbers.MessageViewHeader", "ПРОСМОТР СООБЩЕНИЯ", "MESSAGE VIEW", "消息预览");
        table.Add("SendByNumbers.ProgramActionsHeader", "ДЕЙСТВИЯ ПРОГРАММЫ", "PROGRAM ACTIONS", "程序操作");

        table.Add("SendByNumbers.LogColTime", "Время", "Time", "时间");
        table.Add("SendByNumbers.LogColAccount", "Аккаунт", "Account", "账号");
        table.Add("SendByNumbers.LogColMessage", "Сообщение", "Message", "消息");
        table.Add("SendByNumbers.NoResultsYet", "Результатов ещё нет", "No results yet", "暂无结果");

        table.Add("SendByNumbers.ModalCloseTooltip", "Закрыть", "Close", "关闭");
        table.Add("SendByNumbers.ChooseLocalFileButton", "Выбрать локальный файл", "Choose local file", "选择本地文件");
        table.Add("SendByNumbers.BotUsernameLabel", "Имя пользователя бота", "Bot username", "机器人用户名");
        table.Add("SendByNumbers.PostIdsLabel", "ID поста(ов), по одному в строке", "Post ID(s), one per line", "帖子 ID，每行一个");
        table.Add("SendByNumbers.ModalApplyButton", "Применить", "Apply", "应用");
    }
}
