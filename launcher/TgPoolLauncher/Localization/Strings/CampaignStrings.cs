namespace TgPoolLauncher.Localization.Strings;

internal static class CampaignStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Campaign.SuffixAccountsInvolved", " аккаунтов задействовано", " accounts involved", " 个账户参与");
        table.Add("Campaign.SuffixProxiesActive", " прокси активны", " proxies active", " 个代理已激活");

        table.Add("Campaign.SectionTextTools", "РАБОТА С ТЕКСТОМ", "TEXT TOOLS", "文本工具");
        table.Add("Campaign.TooltipBold", "Жирный (Ctrl+B стиль)", "Bold (Ctrl+B style)", "加粗（Ctrl+B 风格）");
        table.Add("Campaign.TooltipItalic", "Курсив", "Italic", "斜体");
        table.Add("Campaign.TooltipCode", "Моноширинный (код)", "Monospace (code)", "等宽（代码）");
        table.Add("Campaign.TooltipLink", "Вставить ссылку", "Insert link", "插入链接");
        table.Add("Campaign.TooltipForwardSoon", "Скоро: пересылка поста из канала",
            "Soon: forward a post from a channel", "即将推出：转发频道帖子");
        table.Add("Campaign.TooltipAttach", "Прикрепить файл", "Attach file", "附加文件");
        table.Add("Campaign.TooltipBotSoon", "Скоро: рассылка через бота (Postbot)",
            "Soon: sending via bot (Postbot)", "即将推出：通过机器人发送（Postbot）");
        table.Add("Campaign.TooltipTemplatesSoon", "Скоро: шаблоны сообщений",
            "Soon: message templates", "即将推出：消息模板");
        table.Add("Campaign.TooltipInsertPlaceholder", "Вставить {first_name}", "Insert {first_name}", "插入 {first_name}");
        table.Add("Campaign.PlaceholderBold", "жирный текст", "bold text", "粗体文字");
        table.Add("Campaign.PlaceholderItalic", "курсив", "italic", "斜体文字");
        table.Add("Campaign.PlaceholderCode", "код", "code", "代码");
        table.Add("Campaign.PlaceholderLinkText", "текст ссылки", "link text", "链接文字");

        table.Add("Campaign.FieldTarget", "Цель (@username, ссылка на группу или ID)",
            "Target (@username, group link, or ID)", "目标（@用户名、群组链接或 ID）");
        table.Add("Campaign.FieldMessage", "Сообщение", "Message", "消息内容");
        table.Add("Campaign.TooltipClearMessage", "Очистить сообщение", "Clear message", "清空消息");
        table.Add("Campaign.FieldMedia", "Медиа (путь к файлу, опционально)",
            "Media (file path, optional)", "媒体文件（路径，可选）");
        table.Add("Campaign.FieldButtons", "Кнопки ([Текст | https://url], опционально)",
            "Buttons ([Text | https://url], optional)", "按钮（[文本 | https://url]，可选）");

        table.Add("Campaign.PreviewHeader", "ВИД СООБЩЕНИЯ", "MESSAGE PREVIEW", "消息预览");
        table.Add("Campaign.NoTarget", "Цель не указана", "No target set", "未设置目标");
        table.Add("Campaign.TargetKind", "канал / группа", "channel / group", "频道 / 群组");
        table.Add("Campaign.FieldParseMode", "Режим разметки", "Formatting mode", "格式模式");

        table.Add("Campaign.FieldUseDatabase", "Использовать базу данных", "Use database", "使用数据库");
        table.Add("Campaign.FieldMessagesPerAccount", "Кол-во сообщений с одного аккаунта",
            "Messages per account", "每个账户发送数量");
        table.Add("Campaign.FieldDelayBetween", "Задержка между сообщениями (сек)",
            "Delay between messages (sec)", "消息间隔（秒）");
        table.Add("Campaign.FieldFloodWait", "Макс. время ожидания (FloodWait), сек",
            "Max wait time (FloodWait), sec", "最大等待时间（FloodWait，秒）");

        table.Add("Campaign.SectionUsersPrefix", "ПОЛЬЗОВАТЕЛИ: ", "USERS: ", "用户：");
        table.Add("Campaign.DeleteTooltip", "Скоро — рассылка по списку @username",
            "Soon — send to a list of @usernames", "即将推出——按 @用户名 列表发送");
        table.Add("Campaign.UsersPlaceholder",
            "Список @username, каждый с новой строки.\n\n" +
            "Поддерживаемые форматы: '@username', 'username', 'https://t.me/username'.\n\n" +
            "Сейчас рассылка идёт по одной цели (см. поле «Цель» выше) — рассылка по списку пользователей в разработке.",
            "List of @usernames, one per line.\n\n" +
            "Supported formats: '@username', 'username', 'https://t.me/username'.\n\n" +
            "Currently sending goes to a single target (see the “Target” field above) " +
            "— sending to a list of users is in development.",
            "@用户名列表，每行一个。\n\n" +
            "支持的格式：'@username'、'username'、'https://t.me/username'。\n\n" +
            "目前群发仅面向单个目标（见上方“目标”字段）——按用户列表群发功能正在开发中。");

        table.Add("Campaign.SelectAccounts", "Выберите аккаунты", "Select accounts", "选择账户");
        table.Add("Campaign.SelectedPrefix", "Выбрано: ", "Selected: ", "已选：");
        table.Add("Campaign.SelectAccountsButton", "Выбрать аккаунты", "Select accounts", "选择账户");
        table.Add("Campaign.PickerSelectedPrefix", "Выбрано ", "Selected ", "已选 ");
        table.Add("Campaign.OfInfix", " из ", " of ", " / ");
        table.Add("Campaign.PickerNote",
            "Пока не ограничивает список отправителей — рассылка идёт по всему активному пулу.",
            "Doesn't limit the sender list yet — sending goes out across the whole active pool.",
            "暂不限制发送账户列表——群发将面向整个活跃账户池。");

        table.Add("Campaign.ToggleDeleteDialog", "Удалить диалог в аккаунте", "Delete dialog in account", "删除账户中的对话");
        table.Add("Campaign.ToggleForcedCount", "Принудительное количество отправок",
            "Forced send count", "强制发送数量");
        table.Add("Campaign.ToggleLinkPreview", "Предпросмотр ссылок", "Link preview", "链接预览");
        table.Add("Campaign.ToggleSilent", "Режим Silent", "Silent mode", "静默模式");
        table.Add("Campaign.ToggleAutoRepost", "Авторепост", "Auto-repost", "自动转发");
        table.Add("Campaign.TogglePinMessage", "Закрепить сообщение в диалоге", "Pin message in dialog", "在对话中置顶消息");

        table.Add("Campaign.SectionFiles", "ОТПРАВКА ФАЙЛОВ", "FILE SENDING", "文件发送");
        table.Add("Campaign.ToggleVideoNote", "Отправлять видео в кружочке (*.mp4)",
            "Send video as a round video note (*.mp4)", "以圆形视频发送（*.mp4）");
        table.Add("Campaign.ToggleSelfDestruct", "Самоуничтожение файла через 60 секунд",
            "Self-destruct file after 60 seconds", "文件60秒后自毁");

        table.Add("Campaign.SectionActions", "ДЕЙСТВИЯ ПРОГРАММЫ", "PROGRAM ACTIONS", "程序操作");
        table.Add("Campaign.ColTime", "Время", "Time", "时间");
        table.Add("Campaign.ColAccount", "Аккаунт", "Account", "账户");
        table.Add("Campaign.ColMessage", "Сообщение", "Message", "消息");

        table.Add("Campaign.SectionExtra", "ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ", "ADDITIONAL SETTINGS", "更多设置");
        table.Add("Campaign.ToggleScheduled", "Отправка по времени", "Scheduled sending", "定时发送");
        table.Add("Campaign.ToggleThreadControl", "Управление потоками", "Thread management", "线程管理");
        table.Add("Campaign.ToggleAutoStop", "Автоматическая остановка", "Auto-stop", "自动停止");
        table.Add("Campaign.ToggleLaunchControl", "Управление запуском", "Launch control", "启动控制");

        table.Add("Campaign.ProgressSentPrefix", "Отправлено: ", "Sent: ", "已发送：");
        table.Add("Campaign.ProgressErrorsInfix", "  •  Ошибок: ", "  •  Errors: ", "  •  错误：");
        table.Add("Campaign.SendButton", "Запустить", "Send", "发送");
        table.Add("Campaign.GenericError", "ошибка", "error", "错误");
        table.Add("Campaign.MediaDialogTitle", "Выбрать медиафайл", "Select a media file", "选择媒体文件");
        table.Add("Campaign.MediaDialogFilter",
            "Медиа|*.jpg;*.jpeg;*.png;*.gif;*.mp4;*.mov;*.pdf;*.zip|Все файлы|*.*",
            "Media|*.jpg;*.jpeg;*.png;*.gif;*.mp4;*.mov;*.pdf;*.zip|All files|*.*",
            "媒体文件|*.jpg;*.jpeg;*.png;*.gif;*.mp4;*.mov;*.pdf;*.zip|所有文件|*.*");
        table.Add("Campaign.OpenFolderErrorFormat", "Не удалось открыть папку: {0}",
            "Failed to open the folder: {0}", "无法打开文件夹：{0}");
        table.Add("Campaign.LoadAccountsErrorFormat", "Не удалось загрузить аккаунты: {0}",
            "Failed to load accounts: {0}", "无法加载账户：{0}");
    }
}
