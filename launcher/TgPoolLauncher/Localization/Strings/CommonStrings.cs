namespace TgPoolLauncher.Localization.Strings;

internal static class CommonStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Common.Language", "Язык", "Language", "语言");
        table.Add("Common.Browse", "Обзор...", "Browse...", "浏览...");
        table.Add("Common.Refresh", "Обновить", "Refresh", "刷新");
        table.Add("Common.Reset", "Сбросить", "Reset", "重置");
        table.Add("Common.Start", "Старт", "Start", "开始");
        table.Add("Common.Stop", "Стоп", "Stop", "停止");
        table.Add("Common.Cancel", "Отмена", "Cancel", "取消");
        table.Add("Common.Done", "Готово", "Done", "完成");
        table.Add("Common.Open", "Открыть", "Open", "打开");
        table.Add("Common.Delete", "Удалить", "Delete", "删除");
        table.Add("Common.SearchPlaceholder", "Поиск...", "Search...", "搜索...");
        table.Add("Common.ClearLog", "Очистить журнал", "Clear log", "清空日志");
        table.Add("Common.SettingsHeader", "НАСТРОЙКИ", "SETTINGS", "设置");
        table.Add("Common.ResultsHeader", "РЕЗУЛЬТАТЫ", "RESULTS", "结果");
        table.Add("Common.MessagePreviewPlaceholder", "Текст сообщения появится здесь",
            "Message text will appear here", "消息内容将显示在此处");
        table.Add("Common.NotImplementedTooltip", "Скоро — пока не реализовано в бэкенде",
            "Soon — not implemented in the backend yet", "即将推出——后端尚未实现");

        table.Add("BackendClient.StartProxyCheckErrorFormat", "Не удалось запустить проверку прокси ({0}): {1}",
            "Failed to start the proxy check ({0}): {1}", "无法启动代理检测（{0}）：{1}");
        table.Add("BackendClient.StartConversionErrorFormat", "Не удалось запустить конвертацию ({0}): {1}",
            "Failed to start the conversion ({0}): {1}", "无法启动转换（{0}）：{1}");
        table.Add("BackendClient.StartParsingErrorFormat", "Не удалось запустить парсинг ({0}): {1}",
            "Failed to start parsing ({0}): {1}", "无法启动解析（{0}）：{1}");

        table.Add("Nav.Dashboard", "Дашборд", "Dashboard", "仪表盘");
        table.Add("Nav.Accounts", "Аккаунты", "Accounts", "账户");
        table.Add("Nav.AutoRegister", "Авто-регистрация", "Auto Register", "自动注册");
        table.Add("Nav.ProxyCheck", "Прокси", "Proxy", "代理");
        table.Add("Nav.ProxyPoolChecker", "Чекер пула прокси", "Proxy Pool Checker", "代理池检查器");
        table.Add("Nav.Parsing", "Парсинг", "Parsing", "解析");
        table.Add("Nav.JsonGenerator", "JSON-генератор", "JSON Generator", "JSON 生成器");
        table.Add("Nav.Engagement", "Накрутка", "Engagement", "互动增长");
        table.Add("Nav.Stories", "Сторис", "Stories", "快拍");

        table.Add("App.BackendFailedMessage",
            "Не удалось запустить backend-сервис (python -m uvicorn src.api.app:app).\n" +
            "Проверь, что Python и зависимости из requirements.txt установлены.",
            "Failed to start the backend service (python -m uvicorn src.api.app:app).\n" +
            "Check that Python and the requirements.txt dependencies are installed.",
            "无法启动后端服务（python -m uvicorn src.api.app:app）。\n" +
            "请检查是否已安装 Python 及 requirements.txt 中的依赖。");
        table.Add("App.LicenseActivationFailedMessage",
            "Активация лицензии не выполнена. Запусти TgPoolActivator.exe вручную и введи ключ.",
            "License activation was not completed. Run TgPoolActivator.exe manually and enter your key.",
            "许可证激活未完成。请手动运行 TgPoolActivator.exe 并输入密钥。");
    }
}
