namespace TgPoolLauncher.Localization.Strings;

internal static class ToolsStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Tdata.FolderLabel", "Папка с tdata (ищется рекурсивно на любой глубине)",
            "Tdata folder (searched recursively at any depth)", "Tdata 文件夹（将递归搜索任意深度）");
        table.Add("Tdata.OutputLabel", "Папка для .session файлов",
            "Folder for .session files", ".session 文件输出文件夹");
        table.Add("Tdata.AllAccountsCheckbox",
            "Конвертировать все аккаунты из каждой папки (не только основной)",
            "Convert all accounts from each folder (not just the primary one)",
            "转换每个文件夹中的所有账户（不仅是主账户）");
        table.Add("Tdata.ConvertButton", "Конвертировать", "Convert", "转换");
        table.Add("Tdata.ColSource", "Источник", "Source", "来源");
        table.Add("Tdata.ColFile", "Файл", "File", "文件");
        table.Add("Tdata.ColSuccess", "Успех", "Success", "成功");
        table.Add("Tdata.ColError", "Ошибка", "Error", "错误");
        table.Add("Tdata.BrowseTdataDialogTitle", "Выберите папку с tdata",
            "Select the tdata folder", "选择 Tdata 文件夹");
        table.Add("Tdata.BrowseOutputDialogTitle", "Выберите папку для .session файлов",
            "Select the folder for .session files", "选择 .session 文件输出文件夹");

        table.Add("Parsing.NewParsing", "Новый парсинг", "New parsing job", "新建解析任务");
        table.Add("Parsing.SourcesLabel", "Источники (по одному на строку или через запятую)",
            "Sources (one per line or comma-separated)", "来源（每行一个或用逗号分隔）");
        table.Add("Parsing.StrategyLabel", "Стратегия", "Strategy", "策略");
        table.Add("Parsing.TopicIdLabel", "ID топика (только для стратегии topic)",
            "Topic ID (only for the topic strategy)", "话题 ID（仅用于 topic 策略）");
        table.Add("Parsing.FiltersHeader", "Фильтры", "Filters", "筛选条件");
        table.Add("Parsing.LastSeenLabel", "Не в сети дольше (дней), пусто — без фильтра",
            "Offline for longer than (days), empty — no filter", "离线超过（天），留空表示不筛选");
        table.Add("Parsing.GenderLabel", "Пол (male/female/unknown, пусто — без фильтра)",
            "Gender (male/female/unknown, empty — no filter)", "性别（male/female/unknown，留空表示不筛选）");
        table.Add("Parsing.HasAvatarCheckbox", "Только с аватаром", "Avatar only", "仅头像用户");
        table.Add("Parsing.PremiumCheckbox", "Только Premium", "Premium only", "仅 Premium 用户");
        table.Add("Parsing.ExcludeBotsCheckbox", "Исключить ботов", "Exclude bots", "排除机器人");
        table.Add("Parsing.ExportModeLabel", "Формат экспорта", "Export format", "导出格式");
        table.Add("Parsing.ExportPathLabel", "Путь экспорта (пусто — Data\\Exports\\parsed_*)",
            "Export path (empty — Data\\Exports\\parsed_*)", "导出路径（留空则为 Data\\Exports\\parsed_*）");
        table.Add("Parsing.StartButton", "Парсинг", "Start parsing", "开始解析");
        table.Add("Parsing.ProgressHeader", "Ход выполнения", "Progress", "进度");
        table.Add("Parsing.NotRunning", "Не запущен", "Not running", "未运行");
        table.Add("Parsing.Running", "Идёт сбор", "Collecting", "正在采集");
        table.Add("Parsing.CollectedSuffix", " собрано", " collected", " 已采集");
        table.Add("Parsing.ExportFileLabel", "Файл экспорта", "Export file", "导出文件");
        table.Add("Parsing.ExportFilePending", "Появится после завершения",
            "Will appear once finished", "完成后显示");
        table.Add("Parsing.SourcesInProgress", "Источники в обработке", "Sources in progress", "处理中的来源");
        table.Add("Parsing.NoSourcesError", "Укажи хотя бы один источник.",
            "Specify at least one source.", "请至少指定一个来源。");
        table.Add("Parsing.BrowseExportDialogTitle", "Выберите папку для экспорта",
            "Select the export folder", "选择导出文件夹");

        table.Add("SessionConvert.ListLabel",
            "Список сессий (по одной на строку: session_path|json_path|output_subdir)",
            "Session list (one per line: session_path|json_path|output_subdir)",
            "会话列表（每行一个：session_path|json_path|output_subdir）");
        table.Add("SessionConvert.AddFromFolderButton", "Добавить из папки...", "Add from folder...", "从文件夹添加...");
        table.Add("SessionConvert.OutputBaseLabel", "Базовая папка для tdata-выгрузки",
            "Base folder for tdata export", "Tdata 导出的基础文件夹");
        table.Add("SessionConvert.ColFolder", "Папка", "Folder", "文件夹");
        table.Add("SessionConvert.EmptyListError",
            "Список пуст или не распознан (формат: session_path|json_path|output_subdir).",
            "List is empty or unrecognized (format: session_path|json_path|output_subdir).",
            "列表为空或格式无法识别（格式：session_path|json_path|output_subdir）。");
        table.Add("SessionConvert.NoPairsFoundError",
            "В выбранной папке не найдено пар .session+.json.",
            "No .session+.json pairs found in the selected folder.",
            "所选文件夹中未找到 .session+.json 配对文件。");
        table.Add("SessionConvert.BrowseOutputDialogTitle", "Выберите базовую папку для tdata-выгрузки",
            "Select the base folder for tdata export", "选择 Tdata 导出的基础文件夹");
        table.Add("SessionConvert.AddFromFolderDialogTitle", "Выберите папку с .session+.json файлами",
            "Select the folder with .session+.json files", "选择包含 .session+.json 文件的文件夹");
    }
}
