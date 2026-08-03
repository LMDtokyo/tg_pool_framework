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
        table.Add("SendByNumbers.AutoStopSpamblockLabel", "SpamBlock", "SpamBlock", "SpamBlock");
        table.Add("SendByNumbers.AutoStopFloodWaitLabel", "FloodWait", "FloodWait", "FloodWait");
        table.Add("SendByNumbers.AutoStopBanTooltip", "Остановить после стольких заблокированных аккаунтов", "Stop after this many banned accounts", "封禁账号达到此数量后停止");
        table.Add("SendByNumbers.AutoStopSpamBlockTooltip", "Остановить после стольких аккаунтов со SpamBlock", "Stop after this many SpamBlock accounts", "SpamBlock 账号达到此数量后停止");
        table.Add("SendByNumbers.AutoStopFloodWaitTooltip", "Остановить после стольких событий FloodWait", "Stop after this many FloodWait events", "FloodWait 事件达到此数量后停止");
        table.Add("SendByNumbers.RepeatHoursLabel", "Часов повтора", "Repeat hours", "重复小时数");
        table.Add("SendByNumbers.RepeatHoursTooltip", "Интервал повтора в часах", "Repeat interval in hours", "重复间隔（小时）");
        table.Add("SendByNumbers.RequireProxyLabel",
            "Запретить отправку с непрокси-аккаунтов", "Refuse to run on unproxied accounts", "禁止未配置代理的账号执行发送");
        table.Add("SendByNumbers.RequireProxyTooltip",
            "Если включено, рассылка не запустится, пока среди выбранных аккаунтов есть хоть один без прокси",
            "If enabled, the campaign won't start while any selected account has no proxy assigned",
            "启用后，只要所选账号中有任何一个未配置代理，任务就不会启动");

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

        table.Add("SendByNumbers.JobLabelPreview", "Просмотр", "Preview", "预览");
        table.Add("SendByNumbers.PreviewRegenerated", "Создан новый вариант текста.", "Generated a new text variation.", "已生成新的文本变体。");

        table.Add("SendByNumbers.ForwardModalTitle", "Введите ссылку(и) на пост для репоста в канал", "Enter link(s) to post in channel", "输入要转发到频道的帖子链接");
        table.Add("SendByNumbers.ForwardModalSubtitle", "Добавьте по одной ссылке на пост Telegram в каждой строке.", "Add one Telegram post link per line.", "每行添加一个 Telegram 帖子链接。");
        table.Add("SendByNumbers.FileModalTitle", "Добавить файл", "Add file", "添加文件");
        table.Add("SendByNumbers.FileModalSubtitle", "Выберите один или несколько локальных файлов либо введите прямые ссылки на файлы.", "Choose one or more local files, or enter direct file links.", "选择一个或多个本地文件，或输入文件的直接链接。");
        table.Add("SendByNumbers.PostbotModalTitle", "Репост через Postbot", "Repost via Postbot", "通过 Postbot 转发");
        table.Add("SendByNumbers.PostbotModalSubtitle", "Введите имя пользователя бота и один или несколько ID постов.", "Enter the bot username and one or more post IDs.", "输入机器人用户名和一个或多个帖子 ID。");
        table.Add("SendByNumbers.AccountsModalTitle", "Выбор аккаунтов-отправителей", "Select sender accounts", "选择发送账号");
        table.Add("SendByNumbers.AccountsModalSubtitle", "Для этой задачи будут использованы только отмеченные аккаунты.", "Only checked accounts will be used for this job.", "仅使用已勾选的账号执行此任务。");

        table.Add("SendByNumbers.ImportPhoneNumbersDialogTitle", "Импорт номеров телефонов Telegram", "Import Telegram phone numbers", "导入 Telegram 电话号码");
        table.Add("SendByNumbers.PhoneNumbersFileFilter", "Списки номеров телефонов|*.txt;*.csv|Все файлы|*.*", "Phone number lists|*.txt;*.csv|All files|*.*", "电话号码列表|*.txt;*.csv|所有文件|*.*");
        table.Add("SendByNumbers.ImportedNumbersFormat", "Импортировано уникальных номеров: {0}.", "Imported {0} unique number(s).", "已导入 {0} 个唯一号码。");
        table.Add("SendByNumbers.ImportFailedFormat", "Не удалось импортировать {0}: {1}", "Could not import {0}: {1}", "无法导入 {0}：{1}");

        table.Add("SendByNumbers.JobLabelSendByNumbers", "Отправка по номерам", "Send by numbers", "按号码发送");
        table.Add("SendByNumbers.EnterValidPhoneNumber", "Введите хотя бы один действительный номер телефона.", "Enter at least one valid phone number.", "请输入至少一个有效的电话号码。");
        table.Add("SendByNumbers.SelectAtLeastOneAccount", "Выберите хотя бы один аккаунт-отправитель.", "Select at least one sender account.", "请至少选择一个发送账号。");
        table.Add("SendByNumbers.EnterFutureScheduleTime", "Введите будущее местное время в формате yyyy-MM-dd HH:mm.", "Enter a future local time as yyyy-MM-dd HH:mm.", "请输入未来的本地时间，格式为 yyyy-MM-dd HH:mm。");
        table.Add("SendByNumbers.AddMessageContentRequired", "Добавьте текст сообщения, медиа, ссылку для репоста или пост Postbot.", "Add message text, media, a repost link, or a Postbot post.", "请添加消息文本、媒体、转发链接或 Postbot 帖子。");

        table.Add("SendByNumbers.StatusStarting", "Запуск...", "Starting...", "正在启动...");
        table.Add("SendByNumbers.StartedJobFormat", "Задача запущена: {0}.", "Started job {0}.", "任务已启动：{0}。");
        table.Add("SendByNumbers.StatusPollingStopped", "Опрос статуса остановлен.", "Status polling stopped.", "状态轮询已停止。");
        table.Add("SendByNumbers.StatusCouldNotStart", "Не удалось запустить", "Could not start", "无法启动");
        table.Add("SendByNumbers.StopCompleted", "Остановка завершена.", "Stop completed.", "已停止。");
        table.Add("SendByNumbers.StopFailedFormat", "Ошибка остановки: {0}", "Stop failed: {0}", "停止失败：{0}");

        table.Add("SendByNumbers.JobLabelResults", "Результаты", "Results", "结果");
        table.Add("SendByNumbers.CouldNotOpenResultsFormat", "Не удалось открыть результаты: {0}", "Could not open results: {0}", "无法打开结果：{0}");

        table.Add("SendByNumbers.JobLabelRepost", "Репост", "Repost", "转发");
        table.Add("SendByNumbers.RepostLinksClearedText", "Ссылки на репост удалены.", "Post link(s) cleared.", "转发链接已清除。");
        table.Add("SendByNumbers.RepostLinksAddedFormat", "Добавлено ссылок на репост: {0}.", "Added {0} post link(s).", "已添加 {0} 个转发链接。");
        table.Add("SendByNumbers.JobLabelAttachment", "Вложение", "Attachment", "附件");
        table.Add("SendByNumbers.AttachmentsClearedText", "Файлы вложений удалены.", "File(s) cleared.", "附件文件已清除。");
        table.Add("SendByNumbers.AttachmentsAddedFormat", "Добавлено файлов: {0}.", "Added {0} file(s).", "已添加 {0} 个文件。");
        table.Add("SendByNumbers.JobLabelPostbot", "Postbot", "Postbot", "Postbot");
        table.Add("SendByNumbers.PostbotIdsClearedText", "ID постов удалены.", "Post ID(s) cleared.", "帖子 ID 已清除。");
        table.Add("SendByNumbers.PostbotIdsAddedFormat", "Добавлено ID постов: {0}.", "Added {0} post ID(s).", "已添加 {0} 个帖子 ID。");
        table.Add("SendByNumbers.JobLabelAccounts", "Аккаунты", "Accounts", "账号");
        table.Add("SendByNumbers.SelectedAccountsFormat", "Выбрано аккаунтов-отправителей: {0}.", "Selected {0} sender account(s).", "已选择 {0} 个发送账号。");
        table.Add("SendByNumbers.CouldNotLoadAccountsFormat", "Не удалось загрузить аккаунты: {0}", "Could not load accounts: {0}", "无法加载账号：{0}");

        table.Add("SendByNumbers.SelectAttachmentDialogTitle", "Выбор вложения", "Select attachment", "选择附件");
        table.Add("SendByNumbers.AttachmentFileFilter",
            "Поддерживаемые файлы|*.jpg;*.jpeg;*.png;*.gif;*.mp4;*.mov;*.ogg;*.mp3;*.wav;*.pdf;*.zip;*.doc;*.docx;*.xls;*.xlsx|Все файлы|*.*",
            "Supported files|*.jpg;*.jpeg;*.png;*.gif;*.mp4;*.mov;*.ogg;*.mp3;*.wav;*.pdf;*.zip;*.doc;*.docx;*.xls;*.xlsx|All files|*.*",
            "支持的文件|*.jpg;*.jpeg;*.png;*.gif;*.mp4;*.mov;*.ogg;*.mp3;*.wav;*.pdf;*.zip;*.doc;*.docx;*.xls;*.xlsx|所有文件|*.*");
        table.Add("SendByNumbers.UseSelectedAccountsButton", "Использовать выбранные аккаунты", "Use selected accounts", "使用所选账号");

        table.Add("SendByNumbers.ResultsSummaryFormat",
            "Цикл {0}  |  Отправлено {1}  |  Ошибок {2}  |  БАН {3}  |  SpamBlock {4}  |  FloodWait {5}",
            "Cycle {0}  |  Sent {1}  |  Failed {2}  |  BAN {3}  |  SpamBlock {4}  |  FloodWait {5}",
            "周期 {0}  |  已发送 {1}  |  失败 {2}  |  封禁 {3}  |  SpamBlock {4}  |  FloodWait {5}");
        table.Add("SendByNumbers.FinishedFormat", "Завершено: отправлено {0}, ошибок {1}.", "Finished: sent {0}, failed {1}.", "已完成：成功 {0}，失败 {1}。");
        table.Add("SendByNumbers.FinishedWithErrorFormat", "Завершено с ошибкой: {0}", "Finished with error: {0}", "已完成，但出现错误：{0}");
        table.Add("SendByNumbers.CouldNotRestoreJobStatusFormat", "Не удалось восстановить статус задачи: {0}", "Could not restore job status: {0}", "无法恢复任务状态：{0}");

        table.Add("SendByNumbers.MessagePreviewPlaceholder", "Здесь появится предпросмотр сообщения.", "Message preview will appear here.", "消息预览将显示在此处。");

        table.Add("SendByNumbers.RepostLinkCountFormat", "{0} ссылок на репост", "{0} repost link(s)", "{0} 个转发链接");
        table.Add("SendByNumbers.AttachmentSingleFormat", "вложение: {0}", "attachment: {0}", "附件：{0}");
        table.Add("SendByNumbers.AttachmentsCountFormat", "{0} вложений", "{0} attachments", "{0} 个附件");
        table.Add("SendByNumbers.PostbotPostCountFormat", "{0} постов Postbot", "{0} Postbot post(s)", "{0} 个 Postbot 帖子");
    }
}
