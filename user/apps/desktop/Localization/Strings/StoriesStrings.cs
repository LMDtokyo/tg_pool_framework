namespace TgPoolLauncher.Localization.Strings;

internal static class StoriesStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Stories.Title", "Сторис", "Stories", "快拍");
        table.Add("Stories.ActionTypeLabel", "Действие", "Action", "操作类型");
        table.Add("Stories.ActionView", "Просмотр", "View", "浏览");
        table.Add("Stories.ActionReaction", "Реакция", "Reaction", "回应");
        table.Add("Stories.ActionPost", "Публикация", "Post", "发布");
        table.Add("Stories.TargetChatLabel", "Канал/чат (@username или ID)", "Channel/chat (@username or ID)", "频道/群组（@用户名 或 ID）");
        table.Add("Stories.TargetStoryIdLabel", "ID сторис", "Story ID", "快拍 ID");
        table.Add("Stories.ReactionEmojiLabel", "Эмодзи реакции", "Reaction emoji", "反应表情");
        table.Add("Stories.ReactionEmojiTooltip", "Например: ❤️ 🔥 👍 😁", "For example: ❤️ 🔥 👍 😁", "例如：❤️ 🔥 👍 😁");
        table.Add("Stories.MediaPathLabel", "Файл (фото или видео)", "Media file (photo or video)", "媒体文件（图片或视频）");
        table.Add("Stories.CaptionLabel", "Подпись (необязательно)", "Caption (optional)", "说明文字（可选）");
        table.Add("Stories.PrivacyLabel", "Кто увидит", "Who can see it", "谁可以看到");
        table.Add("Stories.PrivacyEveryone", "Все", "Everyone", "所有人");
        table.Add("Stories.PrivacyContacts", "Только контакты", "Contacts only", "仅联系人");
        table.Add("Stories.PeriodHoursLabel", "Часов в архиве", "Hours visible", "展示时长（小时）");
        table.Add("Stories.PeriodHoursTooltip", "Оставьте пустым для стандартных 24 часов", "Leave empty for the standard 24 hours", "留空则默认 24 小时");
        table.Add("Stories.SenderPhonesLabel", "Аккаунты (необязательно)", "Accounts (optional)", "账号（可选）");
        table.Add("Stories.SenderPhonesTooltip",
            "Оставьте пустым, чтобы использовать весь пул", "Leave empty to use the whole pool", "留空则使用整个账号池");

        table.Add("Stories.SmartLimitsHeader", "УМНЫЕ ЛИМИТЫ", "SMART LIMITS", "智能限制");
        table.Add("Stories.StreamsLabel", "Потоки", "Streams", "并发流数");
        table.Add("Stories.StreamsTooltip", "Сколько аккаунтов работают одновременно", "How many accounts work at the same time", "同时工作的账号数量");
        table.Add("Stories.MaxTotalAccountsLabel", "Макс. аккаунтов", "Max accounts", "最大账号数");
        table.Add("Stories.MaxTotalAccountsTooltip",
            "Оставьте пустым, чтобы задействовать весь пул", "Leave empty to use every available account", "留空则使用全部可用账号");
        table.Add("Stories.DelayMinLabel", "Задержка от, сек", "Delay from, sec", "延迟起始，秒");
        table.Add("Stories.DelayMaxLabel", "Задержка до, сек", "Delay to, sec", "延迟结束，秒");
        table.Add("Stories.DailyCapLabel", "Дневной лимит на аккаунт", "Daily cap per account", "每账号每日上限");
        table.Add("Stories.DailyCapTooltip",
            "Требует настроенный Redis; иначе не применяется", "Requires Redis to be configured; otherwise not enforced", "需要配置 Redis，否则不生效");
        table.Add("Stories.MaxFloodWaitLabel", "Макс. ожидание FloodWait, сек", "Max FloodWait wait, sec", "最大 FloodWait 等待，秒");

        table.Add("Stories.AutoStopHeader", "АВТО-СТОП", "AUTO-STOP", "自动停止");
        table.Add("Stories.AutoStopBanLabel", "БАН", "BAN", "封禁");
        table.Add("Stories.AutoStopSpamblockLabel", "SPAMBLOCK", "SPAMBLOCK", "垃圾拦截");
        table.Add("Stories.AutoStopFloodWaitLabel", "FLOODWAIT", "FLOODWAIT", "限流");
        table.Add("Stories.RequireProxyLabel",
            "Запретить отправку с непрокси-аккаунтов", "Refuse to run on unproxied accounts", "禁止未配置代理的账号执行操作");
        table.Add("Stories.RequireProxyTooltip",
            "Если включено, задача не запустится, пока среди выбранных аккаунтов есть хоть один без прокси",
            "If enabled, the job won't start while any selected account has no proxy assigned",
            "启用后，只要所选账号中有任何一个未配置代理，任务就不会启动");

        table.Add("Stories.ChooseMediaTitle", "Выбрать файл", "Choose media file", "选择媒体文件");
        table.Add("Stories.ChooseMediaFilter",
            "Медиафайлы (*.jpg;*.jpeg;*.png;*.mp4;*.mov)|*.jpg;*.jpeg;*.png;*.mp4;*.mov|Все файлы|*.*",
            "Media files (*.jpg;*.jpeg;*.png;*.mp4;*.mov)|*.jpg;*.jpeg;*.png;*.mp4;*.mov|All files|*.*",
            "媒体文件 (*.jpg;*.jpeg;*.png;*.mp4;*.mov)|*.jpg;*.jpeg;*.png;*.mp4;*.mov|所有文件|*.*");

        table.Add("Stories.ProgressHeader", "ПРОГРЕСС", "PROGRESS", "进度");
        table.Add("Stories.NotRunning", "Не запущено", "Not running", "未运行");
        table.Add("Stories.Running", "Выполняется", "Running", "运行中");
        table.Add("Stories.SucceededSuffix", " выполнено", " done", " 已完成");
        table.Add("Stories.FailedLabel", "Неудачно", "Failed", "失败");
        table.Add("Stories.SkippedDailyCapLabel", "Пропущено (лимит)", "Skipped (daily cap)", "跳过（达到上限）");
        table.Add("Stories.BanCountLabel", "Банов", "Bans", "封禁数");
        table.Add("Stories.SpamblockCountLabel", "SpamBlock", "SpamBlock", "垃圾拦截数");
        table.Add("Stories.FloodWaitCountLabel", "FloodWait", "FloodWait", "限流数");
        table.Add("Stories.ExportFileLabel", "Файл результатов", "Results file", "结果文件");
        table.Add("Stories.ResultsHeader", "РЕЗУЛЬТАТЫ ПО АККАУНТАМ", "RESULTS BY ACCOUNT", "各账号结果");
    }
}
