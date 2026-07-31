namespace TgPoolLauncher.Localization.Strings;

internal static class UniversalActivateStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("UniversalActivate.Title", "УНИВЕРСАЛЬНАЯ (АКТИВАЦИЯ)", "UNIVERSAL (ACTIVATE)", "通用（激活）");
        table.Add("UniversalActivate.Subtitle",
            "Настройте универсальную SMS-активацию и параметры аккаунтов по умолчанию",
            "Configure universal SMS activation and account defaults",
            "配置通用 SMS 激活及账号默认参数");
        table.Add("UniversalActivate.NotRunning", "Не выполняется", "Not running", "未运行");

        table.Add("UniversalActivate.UseSmsServiceLabel", "Использовать SMS-сервис", "Use SMS service", "使用 SMS 服务");
        table.Add("UniversalActivate.SmsServiceLabel", "SMS-сервис", "SMS service", "SMS 服务");
        table.Add("UniversalActivate.ProviderCustom", "Другой провайдер", "Custom provider", "自定义服务商");

        table.Add("UniversalActivate.ApiKeyLabel", "API-ключ", "API key", "API 密钥");
        table.Add("UniversalActivate.ApiKeyTooltip",
            "API-ключ от выбранного SMS-сервиса", "API key from the selected SMS service", "所选 SMS 服务的 API 密钥");

        table.Add("UniversalActivate.RegistrationDatabaseLabel", "База данных регистраций", "Registration database", "注册数据库");
        table.Add("UniversalActivate.RegistrationDatabaseTooltip",
            "Путь к базе данных регистраций", "Path to the registration database", "注册数据库的路径");
        table.Add("UniversalActivate.ChooseDatabaseFileTooltip",
            "Выбрать файл базы данных", "Choose database file", "选择数据库文件");

        table.Add("UniversalActivate.BalanceLabel", "Баланс", "Balance", "余额");
        table.Add("UniversalActivate.GetDataButton", "Получить данные", "Get data", "获取数据");

        table.Add("UniversalActivate.AvailableCountriesLabel", "Доступные страны", "Available countries", "可用国家");
        table.Add("UniversalActivate.SelectCountryPlaceholder", "Выберите страну", "Select a country", "选择国家");

        table.Add("UniversalActivate.AvailableOperatorsLabel", "Доступные операторы", "Available operators", "可用运营商");
        table.Add("UniversalActivate.SelectOperatorPlaceholder", "Выберите оператора", "Select an operator", "选择运营商");

        table.Add("UniversalActivate.PricePerSmsLabel", "Цена за SMS", "Price per SMS", "每条短信价格");
        table.Add("UniversalActivate.NumbersAvailableLabel", "Доступно номеров", "Numbers available", "可用号码数量");

        table.Add("UniversalActivate.RegistrationParametersHeader", "ПАРАМЕТРЫ РЕГИСТРАЦИИ", "REGISTRATION PARAMETERS", "注册参数");
        table.Add("UniversalActivate.RegistrationTasksLabel", "Задачи регистрации", "Registration tasks", "注册任务数");
        table.Add("UniversalActivate.SmsTimeoutLabel", "Таймаут SMS (секунды)", "SMS timeout (seconds)", "短信超时（秒）");

        table.Add("UniversalActivate.ActivateFreePrice", "Активировать бесплатную цену", "Activate free price", "启用免费价格激活");
        table.Add("UniversalActivate.ForceVoiceRequest", "Принудительный голосовой запрос", "Force voice request", "强制语音请求");
        table.Add("UniversalActivate.EmulateMobilePhone", "Эмулировать мобильный телефон", "Emulate mobile phone", "模拟手机设备");
        table.Add("UniversalActivate.SetNamesFromFile", "Задавать имена из файла", "Set names from file", "从文件设置姓名");
        table.Add("UniversalActivate.ResetSessionsUnder24h", "Сбрасывать сессии младше 24ч", "Reset sessions under 24h", "重置 24 小时内的会话");
        table.Add("UniversalActivate.ForceReset2FA", "Принудительный сброс 2FA", "Force reset 2FA", "强制重置双重验证");
        table.Add("UniversalActivate.Set2FA", "Установить 2FA", "Set 2FA", "设置双重验证");
        table.Add("UniversalActivate.TurnOffStatistics", "Отключить статистику", "Turn off statistics", "关闭统计");
        table.Add("UniversalActivate.StreamsControl", "Контроль потоков", "Streams control", "并发流控制");
        table.Add("UniversalActivate.ProxySmsRequests", "Проксировать SMS-запросы", "Proxy SMS requests", "通过代理发送短信请求");
        table.Add("UniversalActivate.TemporaryEmail", "Временная почта", "Temporary email", "临时邮箱");
        table.Add("UniversalActivate.RejectCodeSentToApp", "Отклонять код, отправленный в приложение", "Reject code sent to app", "拒绝发送到应用的验证码");

        table.Add("UniversalActivate.ProgramActivityHeader", "АКТИВНОСТЬ ПРОГРАММЫ", "PROGRAM ACTIVITY", "程序活动");
        table.Add("UniversalActivate.ActivitySubtitle",
            "События регистрации будут отображаться здесь", "Registration events will appear here", "注册事件将显示在此处");
        table.Add("UniversalActivate.ClearActivityTooltip", "Очистить активность", "Clear activity", "清空活动");

        table.Add("UniversalActivate.ColTime", "Время", "Time", "时间");
        table.Add("UniversalActivate.ColAccount", "Аккаунт", "Account", "账号");
        table.Add("UniversalActivate.ColMessage", "Сообщение", "Message", "消息");

        table.Add("UniversalActivate.NoEventsYet", "Пока нет событий регистрации", "No registration events yet", "暂无注册事件");
        table.Add("UniversalActivate.EventsCountZero", "0 событий", "0 events", "0 个事件");

        table.Add("UniversalActivate.ImportantInfoHeader", "ВАЖНАЯ ИНФОРМАЦИЯ", "IMPORTANT INFORMATION", "重要信息");
        table.Add("UniversalActivate.ImportantInfoSubtitle",
            "Ознакомьтесь с этими заметками перед началом регистрации",
            "Review these notes before starting registration",
            "开始注册前请阅读以下说明");

        table.Add("UniversalActivate.NumberFilteringTitle", "Фильтрация номеров", "Number filtering", "号码过滤");
        table.Add("UniversalActivate.NumberFilteringBody",
            "Отклоняйте непригодные номера телефонов до начала регистрации. Фильтрация избавляет от трат попыток активации на номера, которые не соответствуют вашим правилам.",
            "Reject unsuitable phone numbers before registration starts. Filtering avoids spending activation attempts on numbers that do not meet your rules.",
            "在注册开始前拒绝不符合要求的电话号码。过滤可避免在不符合规则的号码上浪费激活尝试次数。");

        table.Add("UniversalActivate.SmsTimeoutFallbackTitle", "Таймаут SMS и голосовой резерв", "SMS timeout and voice fallback", "短信超时与语音备用方案");
        table.Add("UniversalActivate.SmsTimeoutFallbackBody",
            "Таймаут определяет, сколько времени задача ждёт код. Голосовой резерв следует включать только тогда, когда он поддерживается выбранным провайдером и страной.",
            "The timeout controls how long a task waits for a code. Voice fallback should only be enabled when it is supported by the selected provider and country.",
            "超时设置控制任务等待验证码的时长。仅当所选服务商和国家支持语音备用方案时才应启用它。");

        table.Add("UniversalActivate.SessionAnd2FATitle", "Настройки сессии и 2FA", "Session and 2FA options", "会话与双重验证选项");
        table.Add("UniversalActivate.SessionAnd2FABody",
            "Настройки сброса и 2FA изменяют сгенерированные файлы аккаунтов. Перед запуском пакета убедитесь в правильности целевой базы данных и настроек прокси.",
            "Reset and 2FA settings change the generated account files. Confirm the destination database and proxy configuration before launching a batch.",
            "重置和双重验证设置会更改生成的账号文件。启动批处理前，请确认目标数据库和代理配置正确无误。");
    }
}
