namespace TgPoolLauncher.Localization.Strings;

internal static class EngagementStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Engagement.Title", "Накрутка", "Engagement", "互动增长");
        table.Add("Engagement.ActionTypeLabel", "Действие", "Action", "操作类型");
        table.Add("Engagement.TargetChatLabel", "Канал/чат (@username или ID)", "Channel/chat (@username or ID)", "频道/群组（@用户名 或 ID）");
        table.Add("Engagement.TargetMessageIdLabel", "ID поста", "Post ID", "帖子 ID");
        table.Add("Engagement.ReactionEmojiLabel", "Эмодзи реакции", "Reaction emoji", "反应表情");
        table.Add("Engagement.ReactionEmojiTooltip", "Например: ❤️ 👍 🔥 😁 😢", "For example: ❤️ 👍 🔥 😁 😢", "例如：❤️ 👍 🔥 😁 😢");
        table.Add("Engagement.PollOptionIndexLabel", "Номер варианта опроса (0 = первый)", "Poll option index (0 = first)", "投票选项序号（0 = 第一个）");
        table.Add("Engagement.PollOptionIndexTooltip", "0 — первый вариант, 1 — второй, и т.д.", "0 is the first option, 1 the second, and so on", "0 表示第一个选项，1 表示第二个，以此类推");
        table.Add("Engagement.CommentTextLabel", "Текст комментария", "Comment text", "评论内容");
        table.Add("Engagement.SenderPhonesLabel", "Аккаунты (необязательно)", "Accounts (optional)", "账号（可选）");
        table.Add("Engagement.SenderPhonesTooltip",
            "Оставьте пустым, чтобы использовать весь пул", "Leave empty to use the whole pool", "留空则使用整个账号池");

        table.Add("Engagement.SmartLimitsHeader", "УМНЫЕ ЛИМИТЫ", "SMART LIMITS", "智能限制");
        table.Add("Engagement.StreamsLabel", "Потоки", "Streams", "并发流数");
        table.Add("Engagement.StreamsTooltip", "Сколько аккаунтов работают одновременно", "How many accounts work at the same time", "同时工作的账号数量");
        table.Add("Engagement.MaxTotalAccountsLabel", "Макс. аккаунтов", "Max accounts", "最大账号数");
        table.Add("Engagement.MaxTotalAccountsTooltip",
            "Оставьте пустым, чтобы задействовать весь пул", "Leave empty to use every available account", "留空则使用全部可用账号");
        table.Add("Engagement.DelayMinLabel", "Задержка от, сек", "Delay from, sec", "延迟起始，秒");
        table.Add("Engagement.DelayMaxLabel", "Задержка до, сек", "Delay to, sec", "延迟结束，秒");
        table.Add("Engagement.DailyCapLabel", "Дневной лимит на аккаунт", "Daily cap per account", "每账号每日上限");
        table.Add("Engagement.DailyCapTooltip",
            "Требует настроенный Redis; иначе не применяется", "Requires Redis to be configured; otherwise not enforced", "需要配置 Redis，否则不生效");
        table.Add("Engagement.MaxFloodWaitLabel", "Макс. ожидание FloodWait, сек", "Max FloodWait wait, sec", "最大 FloodWait 等待，秒");

        table.Add("Engagement.AutoStopHeader", "АВТО-СТОП", "AUTO-STOP", "自动停止");
        table.Add("Engagement.AutoStopBanLabel", "БАН", "BAN", "封禁");
        table.Add("Engagement.AutoStopSpamblockLabel", "SPAMBLOCK", "SPAMBLOCK", "垃圾拦截");
        table.Add("Engagement.AutoStopFloodWaitLabel", "FLOODWAIT", "FLOODWAIT", "限流");
        table.Add("Engagement.RequireProxyLabel",
            "Запретить отправку с непрокси-аккаунтов", "Refuse to run on unproxied accounts", "禁止未配置代理的账号执行操作");
        table.Add("Engagement.RequireProxyTooltip",
            "Если включено, задача не запустится, пока среди выбранных аккаунтов есть хоть один без прокси",
            "If enabled, the job won't start while any selected account has no proxy assigned",
            "启用后，只要所选账号中有任何一个未配置代理，任务就不会启动");

        table.Add("Engagement.ProgressHeader", "ПРОГРЕСС", "PROGRESS", "进度");
        table.Add("Engagement.NotRunning", "Не запущено", "Not running", "未运行");
        table.Add("Engagement.Running", "Выполняется", "Running", "运行中");
        table.Add("Engagement.SucceededSuffix", " выполнено", " done", " 已完成");
        table.Add("Engagement.FailedLabel", "Неудачно", "Failed", "失败");
        table.Add("Engagement.SkippedDailyCapLabel", "Пропущено (лимит)", "Skipped (daily cap)", "跳过（达到上限）");
        table.Add("Engagement.BanCountLabel", "Банов", "Bans", "封禁数");
        table.Add("Engagement.SpamblockCountLabel", "SpamBlock", "SpamBlock", "垃圾拦截数");
        table.Add("Engagement.FloodWaitCountLabel", "FloodWait", "FloodWait", "限流数");
        table.Add("Engagement.ExportFileLabel", "Файл результатов", "Results file", "结果文件");
        table.Add("Engagement.ResultsHeader", "РЕЗУЛЬТАТЫ ПО АККАУНТАМ", "RESULTS BY ACCOUNT", "各账号结果");
    }
}
