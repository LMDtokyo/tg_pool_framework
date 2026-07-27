namespace TgPoolLauncher.Localization.Strings;

internal static class NumberCheckerStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("NumberChecker.SettingsHeader", "НАСТРОЙКИ", "SETTINGS", "设置");
        table.Add("NumberChecker.ResetButton", "Сбросить", "Reset", "重置");
        table.Add("NumberChecker.ResetTooltip", "Сбросить настройки проверщика", "Reset checker settings", "重置检查器设置");

        table.Add("NumberChecker.UseExistingResultsLabel", "Использовать существующие результаты", "Use existing results", "使用已有结果");
        table.Add("NumberChecker.UseBaseDataOnTooltip", "Продолжить незавершённые строки из number_checker.xlsx", "Resume unfinished rows from number_checker.xlsx", "从 number_checker.xlsx 继续未完成的行");
        table.Add("NumberChecker.UseBaseDataOffTooltip", "Ввести номера телефонов вручную", "Enter phone numbers manually", "手动输入电话号码");

        table.Add("NumberChecker.RequestProfileDataLabel", "Запрашивать имя, фамилию, биографию", "Request First name, Last name, Bio", "请求名字、姓氏、个人简介");
        table.Add("NumberChecker.ProfileDataOnTooltip", "Включать данные профиля в результаты", "Include profile details in results", "在结果中包含个人资料");
        table.Add("NumberChecker.ProfileDataOffTooltip", "Проверять только регистрацию", "Check registration only", "仅检查注册状态");

        table.Add("NumberChecker.ResultsWorkbookLabel", "Файл результатов", "Results workbook", "结果工作簿");
        table.Add("NumberChecker.DatabasePathPlaceholder", "Путь к number_checker.xlsx", "Path to number_checker.xlsx", "number_checker.xlsx 路径");
        table.Add("NumberChecker.BrowseDatabaseTooltip", "Выбрать number_checker.xlsx", "Choose number_checker.xlsx", "选择 number_checker.xlsx");

        table.Add("NumberChecker.DelayLabel", "Задержка между запросами", "Delay between requests", "请求间隔");
        table.Add("NumberChecker.DelayMinPlaceholder", "мин  5 сек", "min  5 sec", "最短  5 秒");
        table.Add("NumberChecker.DelayMaxPlaceholder", "макс  10 сек", "max  10 sec", "最长  10 秒");
        table.Add("NumberChecker.FloodWaitLabel", "Максимальное ожидание (FloodWait)", "Maximum timeout (FloodWait)", "最大超时（FloodWait）");
        table.Add("NumberChecker.FloodWaitPlaceholder", "500 сек", "500 sec", "500 秒");
        table.Add("NumberChecker.RequestsPerAccountLabel", "Количество запросов на аккаунт", "Number of requests per account", "每账号请求数");
        table.Add("NumberChecker.RequestsPerAccountPlaceholder", "8 зап", "8 req", "8 次");

        table.Add("NumberChecker.SelectAccountsLabel", "Выбрать аккаунты", "Select Accounts", "选择账号");
        table.Add("NumberChecker.SelectAccountsButton", "Выбрать аккаунты", "Select Accounts", "选择账号");

        table.Add("NumberChecker.GenderDeterminationLabel", "Определение пола", "Gender determination", "性别判定");

        table.Add("NumberChecker.StreamsControlLabel", "Управление потоками", "Streams control", "流控制");
        table.Add("NumberChecker.SimultaneousAccountsLabel", "Одновременных аккаунтов", "Simultaneous accounts", "同时账号数");
        table.Add("NumberChecker.StreamsCountPlaceholder", "4 потока", "4 streams", "4 流");
        table.Add("NumberChecker.DelayBetweenStreamsLabel", "Задержка между потоками", "Delay between streams", "流间隔");
        table.Add("NumberChecker.StreamsDelayPlaceholder", "30–45 сек", "30–45 sec", "30–45 秒");

        table.Add("NumberChecker.ClearButton", "Очистить", "Clear", "清空");
        table.Add("NumberChecker.ClearPhoneNumbersTooltip", "Очистить номера телефонов", "Clear phone numbers", "清除电话号码");
        table.Add("NumberChecker.PhoneNumbersPlaceholder",
            "Список телефонных номеров, каждый с новой строки, в любом формате:\n1(222) 333 4455\n1 222 333 4455\n1-222-333-4455\n12223334455\n\nПрограмма удаляет лишние пробелы, скобки и дефисы. Новые номера добавляются в number_checker.xlsx, существующие строки обновляются.\n\nЕсли работа была прервана, включите «Использовать существующие результаты» и выберите number_checker.xlsx.",
            "List of phone numbers, each one from a new line, in any format:\n1(222) 333 4455\n1 222 333 4455\n1-222-333-4455\n12223334455\n\nThe program removes extra spaces, brackets, and hyphens. New phone numbers are added to number_checker.xlsx and existing rows are updated.\n\nIf work was interrupted, enable Use existing results and choose number_checker.xlsx.",
            "电话号码列表，每行一个，支持任意格式：\n1(222) 333 4455\n1 222 333 4455\n1-222-333-4455\n12223334455\n\n程序会自动去除多余空格、括号和连字符。新号码将添加到 number_checker.xlsx，已有行将更新。\n\n如任务中断，请启用「使用已有结果」并选择 number_checker.xlsx。");

        table.Add("NumberChecker.ProgramActionsHeader", "ДЕЙСТВИЯ ПРОГРАММЫ", "PROGRAM ACTIONS", "程序操作");
        table.Add("NumberChecker.StartTooltip", "Запустить проверщик номеров", "Start number checker", "启动号码检查器");
        table.Add("NumberChecker.StopTooltip", "Остановить проверщик номеров", "Stop number checker", "停止号码检查器");
        table.Add("NumberChecker.ClearActionsTooltip", "Очистить действия", "Clear actions", "清除操作记录");

        table.Add("NumberChecker.LogColTime", "Время", "Time", "时间");
        table.Add("NumberChecker.LogColAccount", "Аккаунт", "Account", "账号");
        table.Add("NumberChecker.LogColMessage", "Сообщение", "Message", "消息");

        table.Add("NumberChecker.ResultsHeader", "РЕЗУЛЬТАТЫ", "RESULTS", "结果");
        table.Add("NumberChecker.NoResultsYet", "Результатов ещё нет", "No results yet", "暂无结果");
        table.Add("NumberChecker.OpenResultsTooltip", "Открыть папку результатов", "Open results folder", "打开结果文件夹");
        table.Add("NumberChecker.OpenButton", "Открыть", "Open", "打开");

        table.Add("NumberChecker.SelectAccountsDialogTitle", "Выбрать аккаунты", "Select Accounts", "选择账号");
        table.Add("NumberChecker.SelectAccountsDialogSubtitle",
            "Выберите активные аккаунты для проверки телефонных номеров.",
            "Choose the active accounts that will check phone numbers.",
            "选择将用于检查电话号码的活跃账号。");
        table.Add("NumberChecker.AccountsStatusLoading", "Загрузка аккаунтов…", "Loading accounts…", "正在加载账号…");
        table.Add("NumberChecker.CancelButton", "Отмена", "Cancel", "取消");
        table.Add("NumberChecker.UseSelectedAccountsButton", "Использовать выбранные аккаунты", "Use selected accounts", "使用所选账号");
        table.Add("NumberChecker.CloseTooltip", "Закрыть", "Close", "关闭");
    }
}
