namespace TgPoolLauncher.Localization.Strings;

internal static class SmsPoolStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("SmsPool.ServiceLabel", "SMS-сервис", "SMS service", "短信服务");
        table.Add("SmsPool.ApiKeyLabel", "API-ключ", "API key", "API 密钥");
        table.Add("SmsPool.BalanceLabel", "Баланс", "Balance", "余额");
        table.Add("SmsPool.RefreshBalance", "Обновить", "Refresh", "刷新");

        table.Add("SmsPool.ActivationSectionHeader", "АКТИВАЦИЯ TELEGRAM", "TELEGRAM ACTIVATION", "TELEGRAM 激活");
        table.Add("SmsPool.CountryLabel", "Страна", "Country", "国家");
        table.Add("SmsPool.CountrySearchTooltip", "Поиск стран по названию или id", "Search countries by name or id", "按名称或 ID 搜索国家");
        table.Add("SmsPool.LoadCountries", "Загрузить", "Load", "加载");
        table.Add("SmsPool.OperatorLabel", "Оператор", "Operator", "运营商");
        table.Add("SmsPool.RefreshCatalog", "Обновить", "Refresh", "刷新");
        table.Add("SmsPool.OperatorsAutoLoadNote",
            "Операторы и доступность загружаются автоматически после выбора страны.",
            "Operators and availability load automatically after country selection.",
            "选择国家后，运营商及号码可用情况会自动加载。");

        table.Add("SmsPool.StartPriceLabel", "Начальная цена", "Start price", "起始价格");
        table.Add("SmsPool.PurchaseCeilingLabel", "Потолок закупки", "Purchase ceiling", "采购价格上限");
        table.Add("SmsPool.CeilingExplanationNote",
            "Если у начальной цены нет числовых значений, покупки поднимаются по более высоким уровням вплоть до этого потолка.",
            "If the start price has no numbers, purchases climb higher tiers up to this ceiling.",
            "如果起始价格没有具体数值，采购会逐级上涨，直到达到此价格上限。");

        table.Add("SmsPool.AccountsToCreateLabel", "Аккаунтов создать", "Accounts to create", "要创建的账号数");
        table.Add("SmsPool.ConcurrentPhonesLabel", "Одновременных номеров (1–10)", "Concurrent phones (1–10)", "并发号码数（1–10）");
        table.Add("SmsPool.SmsTimeoutLabel", "Тайм-аут SMS, сек (30–1200)", "SMS timeout, seconds (30–1200)", "短信超时，秒（30–1200）");
        table.Add("SmsPool.PoolBehaviorNote",
            "Приложение поддерживает заданное количество активных номеров, пока не будет достигнута цель по аккаунтам. Неудачные попытки автоматически заменяются.",
            "The app keeps the configured number of phones active until the account target is reached. Failed attempts are replaced automatically.",
            "应用会保持设定数量的号码处于活动状态，直到达到账号目标为止。失败的尝试会自动被替换。");

        table.Add("SmsPool.ActivityHeader", "АКТИВНОСТЬ АКТИВАЦИИ", "ACTIVATION ACTIVITY", "激活活动");
        table.Add("SmsPool.ActivitySubtitle",
            "Купленные номера и входящие коды Telegram появляются здесь",
            "Purchased numbers and incoming Telegram codes appear here",
            "已购号码和收到的 Telegram 验证码会显示在此处");
        table.Add("SmsPool.StartTooltip", "Запустить активации", "Start activations", "开始激活");
        table.Add("SmsPool.StopTooltip", "Остановить и отменить ожидающие активации", "Stop and cancel pending activations", "停止并取消待处理的激活");
        table.Add("SmsPool.ClearTooltip", "Очистить завершённую активность", "Clear completed activity", "清除已完成的活动记录");

        table.Add("SmsPool.ColTime", "Время", "Time", "时间");
        table.Add("SmsPool.ColPhone", "Номер", "Phone", "号码");
        table.Add("SmsPool.ColOperator", "Оператор", "Operator", "运营商");
        table.Add("SmsPool.ColCost", "Стоимость", "Cost", "费用");
        table.Add("SmsPool.ColStage", "Этап", "Stage", "阶段");
        table.Add("SmsPool.ColCode", "Код", "Code", "验证码");
        table.Add("SmsPool.ColMessage", "Сообщение", "Message", "消息");

        table.Add("SmsPool.PendingActivationsNote",
            "Ожидающие активации отменяются при остановке или по тайм-ауту.",
            "Pending activations are canceled on Stop or timeout.",
            "待处理的激活会在点击停止或超时后取消。");
        table.Add("SmsPool.EventsSuffix", " событий", " events", " 个事件");

        table.Add("SmsPool.TwoFactorHeader", "ДВУХФАКТОРНАЯ ПРОВЕРКА TELEGRAM", "TELEGRAM 2-STEP VERIFICATION", "TELEGRAM 两步验证");
        table.Add("SmsPool.TwoFactorPromptPrefix",
            "Введите облачный пароль для ", "Enter the cloud password for ", "输入云密码，账号：");
        table.Add("SmsPool.Submit2FA", "Отправить 2FA", "Submit 2FA", "提交两步验证");

        table.Add("SmsPool.ImportantInfoHeader", "ВАЖНАЯ ИНФОРМАЦИЯ", "IMPORTANT INFORMATION", "重要信息");
        table.Add("SmsPool.RealPurchasesTitle", "Реальные покупки", "Real purchases", "真实购买");
        table.Add("SmsPool.PriceAvailabilityTitle", "Цена и доступность", "Price and availability", "价格与可用性");
        table.Add("SmsPool.LifecycleTitle", "Жизненный цикл", "Lifecycle", "生命周期");
        table.Add("SmsPool.LifecycleExplanationNote",
            "Приложение заменяет неудачные попытки, поддерживает заданный пул полным и останавливается, когда создано запрошенное количество новых аккаунтов.",
            "The app replaces failed attempts, keeps the configured pool full, and stops when the requested number of new accounts has been created.",
            "应用会替换失败的尝试，保持设定的号码池始终充足，并在创建所需数量的新账号后自动停止。");
    }
}
