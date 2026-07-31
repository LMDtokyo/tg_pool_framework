namespace TgPoolLauncher.Localization.Strings;

internal static class HeroSmsStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("HeroSms.AccountHeader", "АККАУНТ HERO SMS", "HERO SMS ACCOUNT", "HERO SMS 账户");
        table.Add("HeroSms.ServiceLabel", "SMS-сервис", "SMS service", "短信服务");
        table.Add("HeroSms.ApiKeyLabel", "API-ключ", "API key", "API 密钥");
        table.Add("HeroSms.ApiKeyTooltip",
            "Ваш API-ключ Hero SMS хранится только в памяти", "Your Hero SMS API key is kept in memory only", "您的 Hero SMS API 密钥仅保存在内存中");
        table.Add("HeroSms.ApiKeyNote",
            "Ключ отправляется только на локальный бэкенд и в Hero SMS.", "The key is sent only to the local backend and Hero SMS.", "该密钥仅发送至本地后端和 Hero SMS。");
        table.Add("HeroSms.BalanceLabel", "Баланс", "Balance", "余额");

        table.Add("HeroSms.ActivationHeader", "АКТИВАЦИЯ TELEGRAM", "TELEGRAM ACTIVATION", "TELEGRAM 激活");
        table.Add("HeroSms.CountryLabel", "Страна", "Country", "国家");
        table.Add("HeroSms.CountrySearchTooltip",
            "Поиск стран по названию или id", "Search countries by name or id", "按名称或 ID 搜索国家");
        table.Add("HeroSms.LoadButton", "Загрузить", "Load", "加载");
        table.Add("HeroSms.OperatorLabel", "Оператор", "Operator", "运营商");
        table.Add("HeroSms.OperatorAutoLoadNote",
            "Операторы и доступность загружаются автоматически после выбора страны.",
            "Operators and availability load automatically after country selection.",
            "选择国家后，运营商和可用数量将自动加载。");

        table.Add("HeroSms.StartPriceLabel", "Начальная цена", "Start price", "起始价格");
        table.Add("HeroSms.PurchaseCeilingLabel", "Потолок закупки", "Purchase ceiling", "采购价格上限");
        table.Add("HeroSms.PurchaseCeilingNote",
            "Если по начальной цене нет номеров, покупки поднимаются по более высоким тарифам вплоть до этого потолка.",
            "If the start price has no numbers, purchases climb higher tiers up to this ceiling.",
            "若起始价格没有可用号码，采购将逐级提高价位，直至达到该上限。");

        table.Add("HeroSms.AccountsToCreateLabel", "Аккаунтов создать", "Accounts to create", "待创建账户数");
        table.Add("HeroSms.ConcurrentPhonesLabel", "Одновременных номеров (1–10)", "Concurrent phones (1–10)", "并发号码数（1–10）");
        table.Add("HeroSms.SmsTimeoutLabel", "Таймаут SMS, сек (30–1200)", "SMS timeout, seconds (30–1200)", "短信超时（秒，30–1200）");
        table.Add("HeroSms.PhonesActiveNote",
            "Приложение поддерживает заданное число активных номеров, пока не будет достигнута цель по аккаунтам. Неудачные попытки заменяются автоматически.",
            "The app keeps the configured number of phones active until the account target is reached. Failed attempts are replaced automatically.",
            "应用会保持设定数量的号码处于活动状态，直到达到账户目标。失败的尝试会自动替换。");

        table.Add("HeroSms.ActivityHeader", "АКТИВНОСТЬ АКТИВАЦИЙ", "ACTIVATION ACTIVITY", "激活活动");
        table.Add("HeroSms.ActivitySubheader",
            "Здесь отображаются купленные номера и входящие коды Telegram",
            "Purchased numbers and incoming Telegram codes appear here",
            "此处显示已购买的号码和收到的 Telegram 验证码");
        table.Add("HeroSms.StartActivationsTooltip", "Запустить активации", "Start activations", "开始激活");
        table.Add("HeroSms.StopActivationsTooltip",
            "Остановить и отменить ожидающие активации", "Stop and cancel pending activations", "停止并取消待处理的激活");
        table.Add("HeroSms.ClearActivityTooltip",
            "Очистить завершённую активность", "Clear completed activity", "清除已完成的活动记录");

        table.Add("HeroSms.ColTime", "Время", "Time", "时间");
        table.Add("HeroSms.ColPhone", "Номер", "Phone", "号码");
        table.Add("HeroSms.ColOperator", "Оператор", "Operator", "运营商");
        table.Add("HeroSms.ColCost", "Стоимость", "Cost", "费用");
        table.Add("HeroSms.ColStage", "Этап", "Stage", "阶段");
        table.Add("HeroSms.ColCode", "Код", "Code", "验证码");
        table.Add("HeroSms.ColMessage", "Сообщение", "Message", "消息");

        table.Add("HeroSms.PendingCanceledNote",
            "Ожидающие активации отменяются при остановке или таймауте.",
            "Pending activations are canceled on Stop or timeout.",
            "待处理的激活会在停止或超时后被取消。");
        table.Add("HeroSms.EventsSuffix", " событий", " events", " 条事件");

        table.Add("HeroSms.TwoFactorHeader", "ДВУХЭТАПНАЯ ПРОВЕРКА TELEGRAM", "TELEGRAM 2-STEP VERIFICATION", "TELEGRAM 两步验证");
        table.Add("HeroSms.TwoFactorPromptPrefix",
            "Введите облачный пароль для номера ", "Enter the cloud password for ", "请输入云密码，号码：");
        table.Add("HeroSms.SubmitTwoFactorButton", "Отправить 2FA", "Submit 2FA", "提交两步验证");

        table.Add("HeroSms.ImportantInfoHeader", "ВАЖНАЯ ИНФОРМАЦИЯ", "IMPORTANT INFORMATION", "重要信息");
        table.Add("HeroSms.ImportantInfoSubheader",
            "Как работает эта интеграция с Hero SMS", "How this Hero SMS integration behaves", "此 Hero SMS 集成的工作方式");
        table.Add("HeroSms.RealPurchasesHeader", "Реальные покупки", "Real purchases", "真实购买");
        table.Add("HeroSms.RealPurchasesText",
            "Автоматическая регистрация может списывать средства с вашего баланса Hero SMS. Сначала проверьте выбранную страну, цель, параллелизм и отображаемую максимальную цену.",
            "Automatic registration can deduct funds from your Hero SMS balance. Verify the selected country, target, concurrency, and displayed maximum price first.",
            "自动注册可能会从您的 Hero SMS 余额中扣款。请先确认所选国家、目标数量、并发数以及显示的最高价格。");
        table.Add("HeroSms.PriceAvailabilityHeader", "Цена и доступность", "Price and availability", "价格与可用性");
        table.Add("HeroSms.PriceAvailabilityText",
            "Hero SMS возвращает цену и доступность Telegram по стране на уровне каталога. Выбор оператора применяется при покупке; фактическая стоимость указывается в ответе на запрос покупки.",
            "Hero SMS returns catalog-level Telegram price and availability by country. Operator selection applies when purchasing; actual cost is reported by the purchase response.",
            "Hero SMS 按国家返回目录级别的 Telegram 价格和可用数量。运营商的选择在购买时生效；实际费用以购买响应中的数据为准。");
        table.Add("HeroSms.LifecycleHeader", "Жизненный цикл", "Lifecycle", "生命周期");
        table.Add("HeroSms.LifecycleText",
            "Приложение заменяет неудачные попытки, поддерживает заданный пул заполненным и останавливается, когда создано запрошенное количество новых аккаунтов.",
            "The app replaces failed attempts, keeps the configured pool full, and stops when the requested number of new accounts has been created.",
            "应用会自动替换失败的尝试，保持设定的号码池处于满员状态，并在创建完请求数量的新账户后自动停止。");

        table.Add("HeroSms.BalancePlaceholder", "USD  0.00", "USD  0.00", "USD  0.00");
        table.Add("HeroSms.BalanceFormat", "USD  {0}", "USD  {0}", "USD  {0}");
        table.Add("HeroSms.TelegramUnavailableInCountry",
            "Telegram недоступен в этой стране",
            "Telegram is unavailable in this country",
            "该国家/地区不支持 Telegram");
        table.Add("HeroSms.CatalogSummaryFormat",
            "{0} операторов · {1} ценовых уровней · {2}: {3}",
            "{0} operators · {1} price tiers · {2}: {3}",
            "{0} 个运营商 · {1} 个价格档位 · {2}：{3}");
        table.Add("HeroSms.PriceOptionFormat",
            "USD  {0}  ·  {1} шт.",
            "USD  {0}  ·  {1} pcs",
            "USD  {0}  ·  {1} 个");
        table.Add("HeroSms.RegistrationStartedFormat",
            "Регистрация {0} запущена",
            "{0} registration started",
            "{0} 注册已开始");
        table.Add("HeroSms.StoppingCanceling",
            "Остановка и отмена активных покупок...",
            "Stopping and canceling active purchases...",
            "正在停止并取消正在进行的购买...");
        table.Add("HeroSms.ActivationBatchStoppedFormat",
            "Пакет активаций {0} остановлен",
            "{0} activation batch stopped",
            "{0} 激活批次已停止");
        table.Add("HeroSms.TwoFactorSubmittedFormat",
            "Двухэтапная проверка отправлена для {0}",
            "2-step verification submitted for {0}",
            "已为 {0} 提交两步验证");
        table.Add("HeroSms.CreatedProgressFormat",
            "Создано {0} / {1} аккаунтов · {2} активно",
            "Created {0} / {1} accounts · {2} active",
            "已创建 {0} / {1} 个账户 · {2} 个进行中");
        table.Add("HeroSms.RegistrationCompleteFormat",
            "Регистрация завершена: {0} / {1} аккаунтов создано",
            "Registration complete: {0} / {1} accounts created",
            "注册完成：已创建 {0} / {1} 个账户");
        table.Add("HeroSms.RegistrationStoppedFormat",
            "Регистрация остановлена: {0} / {1} аккаунтов создано",
            "Registration stopped: {0} / {1} accounts created",
            "注册已停止：已创建 {0} / {1} 个账户");
        table.Add("HeroSms.SelectCountryPlaceholder", "Выберите страну", "Select a country", "选择国家");
        table.Add("HeroSms.SelectOperatorPlaceholder", "Выберите оператора", "Select an operator", "选择运营商");
        table.Add("HeroSms.CountriesLoadedFormat",
            "Загружено стран: {0}",
            "{0} countries loaded",
            "已加载 {0} 个国家");
        table.Add("HeroSms.CountriesShownFormat",
            "Показано {0} из {1} стран",
            "{0} of {1} countries shown",
            "已显示 {1} 个国家中的 {0} 个");

        table.Add("HeroSms.AvailabilityLabel", "Доступно номеров", "Numbers available", "可用号码数");
        table.Add("HeroSms.AnyOperatorOption", "любой", "any", "任意");

        table.Add("HeroSms.SmsPool.AvailabilityLabel", "Процент успеха", "Success rate", "成功率");
        table.Add("HeroSms.SmsPool.AccountHeader", "АККАУНТ SMSPOOL", "SMSPOOL ACCOUNT", "SMSPOOL 账户");
        table.Add("HeroSms.SmsPool.ApiKeyToolTip",
            "Ваш API-ключ SMSpool хранится только в памяти",
            "Your SMSpool API key is kept in memory only",
            "您的 SMSpool API 密钥仅保存在内存中");
        table.Add("HeroSms.SmsPool.KeyPrivacyMessage",
            "Ключ отправляется только на локальный бэкенд и в SMSpool.",
            "The key is sent only to the local backend and SMSpool.",
            "该密钥仅发送至本地后端和 SMSpool。");
        table.Add("HeroSms.SmsPool.IntegrationBehaviorTitle",
            "Как работает эта интеграция с SMSpool",
            "How this SMSpool integration behaves",
            "此 SMSpool 集成的工作方式");
        table.Add("HeroSms.SmsPool.PurchaseWarning",
            "Автоматическая регистрация может списывать средства с вашего баланса SMSpool. Сначала проверьте цель, параллелизм и отображаемую максимальную цену.",
            "Automatic registration can deduct funds from your SMSpool balance. Verify the target, concurrency, and displayed maximum price first.",
            "自动注册可能会从您的 SMSpool 余额中扣款。请先确认目标数量、并发数以及显示的最高价格。");
        table.Add("HeroSms.SmsPool.PriceAvailabilityNote",
            "SMSpool возвращает цену Telegram и процент успеха по стране, а не актуальное количество доступных номеров. Покупки всё равно выполняются через совместимый endpoint SMSpool.",
            "SMSpool returns Telegram price and country success rate, not a live available-number count. Purchases are still attempted through SMSpool's compatible endpoint.",
            "SMSpool 返回的是 Telegram 价格和国家成功率，而非实时可用号码数量。购买仍通过 SMSpool 的兼容接口进行。");

        table.Add("HeroSms.GrizzlySms.AccountHeader", "АККАУНТ GRIZZLYSMS", "GRIZZLYSMS ACCOUNT", "GRIZZLYSMS 账户");
        table.Add("HeroSms.GrizzlySms.ApiKeyToolTip",
            "Ваш API-ключ GrizzlySMS хранится только в памяти",
            "Your GrizzlySMS API key is kept in memory only",
            "您的 GrizzlySMS API 密钥仅保存在内存中");
        table.Add("HeroSms.GrizzlySms.KeyPrivacyMessage",
            "Ключ отправляется только на локальный бэкенд и в GrizzlySMS.",
            "The key is sent only to the local backend and GrizzlySMS.",
            "该密钥仅发送至本地后端和 GrizzlySMS。");
        table.Add("HeroSms.GrizzlySms.IntegrationBehaviorTitle",
            "Как работает эта интеграция с GrizzlySMS",
            "How this GrizzlySMS integration behaves",
            "此 GrizzlySMS 集成的工作方式");
        table.Add("HeroSms.GrizzlySms.PurchaseWarning",
            "Автоматическая регистрация может списывать средства с вашего баланса GrizzlySMS. Сначала проверьте цель, параллелизм и отображаемую максимальную цену.",
            "Automatic registration can deduct funds from your GrizzlySMS balance. Verify the target, concurrency, and displayed maximum price first.",
            "自动注册可能会从您的 GrizzlySMS 余额中扣款。请先确认目标数量、并发数以及显示的最高价格。");
        table.Add("HeroSms.GrizzlySms.PriceAvailabilityNote",
            "GrizzlySMS возвращает цену и доступность Telegram по стране. Покупки используют задокументированное действие getNumberV2, а выбранная цена каталога передаётся как maxPrice.",
            "GrizzlySMS returns Telegram price and availability by country. Purchases use its documented getNumberV2 action and the selected catalog price as maxPrice.",
            "GrizzlySMS 按国家返回 Telegram 价格和可用数量。购买使用其文档化的 getNumberV2 操作，所选目录价格将作为 maxPrice 传递。");
    }
}
