namespace TgPoolLauncher.Localization.Strings;

internal static class DatamollStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Datamoll.SectionProvider", "ПРОВАЙДЕР DATAMOLL", "DATAMOLL PROVIDER", "DATAMOLL 提供商");
        table.Add("Datamoll.ServiceLabel", "Сервис", "Service", "服务");
        table.Add("Datamoll.ApiKeyLabel", "API-ключ", "API key", "API 密钥");
        table.Add("Datamoll.ApiKeyTooltip", "API-ключ провайдера Datamoll", "Datamoll Provider API key", "Datamoll 提供商 API 密钥");
        table.Add("Datamoll.ApiSecretLabel", "API-секрет", "API secret", "API 密文");
        table.Add("Datamoll.ApiSecretTooltip", "API-секрет провайдера Datamoll", "Datamoll Provider API secret", "Datamoll 提供商 API 密文");
        table.Add("Datamoll.CredentialsNote",
            "Учётные данные хранятся в памяти и передаются только локальному бэкенду и Datamoll.",
            "Credentials stay in memory and are sent only to the local backend and Datamoll.",
            "凭据仅保存在内存中，仅发送到本地后端和 Datamoll。");

        table.Add("Datamoll.BalanceLabel", "Доступный баланс", "Available balance", "可用余额");
        table.Add("Datamoll.RefreshBalanceTooltip", "Обновить баланс", "Refresh balance", "刷新余额");

        table.Add("Datamoll.SectionTelegramProduct", "TELEGRAM ПРОДУКТ", "TELEGRAM PRODUCT", "TELEGRAM 产品");
        table.Add("Datamoll.SearchCountryLabel", "Поиск страны", "Search country", "搜索国家");
        table.Add("Datamoll.SearchCountryTooltip", "Поиск по названию страны", "Search by country name", "按国家名称搜索");
        table.Add("Datamoll.LoadCatalogTooltip", "Загрузить актуальный каталог", "Load live catalog", "加载实时目录");

        table.Add("Datamoll.ColumnCountry", "Страна", "Country", "国家");
        table.Add("Datamoll.ColumnAge", "Возраст", "Age", "账龄");
        table.Add("Datamoll.ColumnPrice", "Цена", "Price", "价格");
        table.Add("Datamoll.ColumnAvailable", "Доступно", "Available", "可用数量");

        table.Add("Datamoll.SectionSelectedProduct", "ВЫБРАННЫЙ ПРОДУКТ", "SELECTED PRODUCT", "已选产品");
        table.Add("Datamoll.SelectedCountryLabel", "Страна", "Country", "国家");
        table.Add("Datamoll.SelectedAgeLabel", "Возраст", "Age", "账龄");
        table.Add("Datamoll.SelectedPriceLabel", "Цена", "Price", "价格");
        table.Add("Datamoll.SelectedAvailableLabel", "Доступно", "Available", "可用数量");
        table.Add("Datamoll.QuantityLabel", "Количество", "Quantity", "数量");
        table.Add("Datamoll.AllowedQuantityLabel", "Допустимое количество", "Allowed quantity", "允许数量");
        table.Add("Datamoll.OrderTotalLabel", "Итого по заказу", "Order total", "订单总额");
        table.Add("Datamoll.PurchaseButton", "Купить", "Purchase", "购买");

        table.Add("Datamoll.SectionActivity", "АКТИВНОСТЬ ПОКУПОК", "PURCHASE ACTIVITY", "购买活动");
        table.Add("Datamoll.ActivitySubtitle", "Актуальный статус заказов Datamoll", "Live Datamoll order status", "Datamoll 实时订单状态");
        table.Add("Datamoll.ClearActivityTooltip", "Очистить активность", "Clear activity", "清空活动");
        table.Add("Datamoll.ActivityColumnTime", "Время", "Time", "时间");
        table.Add("Datamoll.ActivityColumnOrder", "Заказ", "Order", "订单");
        table.Add("Datamoll.ActivityColumnProduct", "Продукт", "Product", "产品");
        table.Add("Datamoll.ActivityColumnQty", "Кол-во", "Qty", "数量");
        table.Add("Datamoll.ActivityColumnTotal", "Итого", "Total", "总计");
        table.Add("Datamoll.ActivityColumnStatus", "Статус", "Status", "状态");
        table.Add("Datamoll.ActivityColumnDelivered", "Доставлено", "Delivered", "已交付");
        table.Add("Datamoll.ActivityColumnMessage", "Сообщение", "Message", "消息");
        table.Add("Datamoll.OrdersCountSuffix", " заказов", " orders", " 订单");

        table.Add("Datamoll.SectionDelivery", "ДОСТАВКА DATAMOLL", "DATAMOLL DELIVERY", "DATAMOLL 交付");
        table.Add("Datamoll.DeliverySubtitle",
            "Готовые продукты Telegram-аккаунтов приобретаются напрямую из каталога.",
            "Prepared Telegram account products are purchased directly from the catalog.",
            "已准备好的 Telegram 账号产品直接从目录购买。");
        table.Add("Datamoll.DeliveryNote1",
            "Покупки реальны и списывают отображаемый баланс Datamoll. Наличие и цена проверяются повторно при оформлении заказа.",
            "Purchases are real and deduct the displayed Datamoll balance. Stock and price are checked again when the order is placed.",
            "购买是真实的，将从显示的 Datamoll 余额中扣除。下单时将再次检查库存和价格。");
        table.Add("Datamoll.DeliveryNote2",
            "Повторная попытка использует тот же идентификатор заказа, что позволяет Datamoll восстановить задержанный заказ без двойного списания.",
            "A retry reuses the same order identity, allowing Datamoll to recover delayed orders without charging twice.",
            "重试将复用相同的订单标识，使 Datamoll 能够恢复延迟订单而不重复扣费。");
        table.Add("Datamoll.DeliveryNote3",
            "Доставленные пакеты загружаются автоматически. Сессионные аккаунты добавляются в Accounts, данные Telegram Desktop — в Tdata, а приватный чек заказа сохраняется.",
            "Delivered packages are downloaded automatically. Session accounts are added to Accounts, Telegram Desktop data is added to Tdata, and the private order receipt is retained.",
            "已交付的包会自动下载。会话账号添加到 Accounts，Telegram Desktop 数据添加到 Tdata，私有订单收据将被保留。");

        table.Add("Datamoll.BalanceNotLoaded", "Не загружено", "Not loaded", "尚未加载");
        table.Add("Datamoll.CatalogStatusLoadPrompt",
            "Загрузите актуальный каталог, чтобы выбрать Telegram продукт.",
            "Load the live catalog to select a Telegram product.",
            "加载实时目录以选择 Telegram 产品。");
        table.Add("Datamoll.ProductDescriptionPlaceholder",
            "Выберите продукт, чтобы увидеть описание доставки.",
            "Select a product to see its delivery description.",
            "选择产品以查看其交付说明。");
        table.Add("Datamoll.NotSpecified", "Не указано", "Not specified", "未指定");
        table.Add("Datamoll.BalanceAvailableFormat",
            "{0} {1} доступно  (баланс {2}, кредитный лимит {3})",
            "{0} {1} available  (balance {2}, credit {3})",
            "{0} {1} 可用（余额 {2}，信用额度 {3}）");
        table.Add("Datamoll.CatalogLoading",
            "Загрузка товаров Telegram в наличии...",
            "Loading in-stock Telegram products...",
            "正在加载有库存的 Telegram 产品...");
        table.Add("Datamoll.CatalogEmpty",
            "Товары Telegram в наличии сейчас недоступны.",
            "No in-stock Telegram products are currently available.",
            "当前没有可用的 Telegram 库存产品。");
        table.Add("Datamoll.CatalogShownFormat",
            "Показано {0} из {1} товаров Telegram в наличии.",
            "{0} of {1} in-stock Telegram products shown.",
            "已显示 {1} 个有库存 Telegram 产品中的 {0} 个。");
        table.Add("Datamoll.NoCountriesMatchFormat",
            "Нет стран, соответствующих \"{0}\".",
            "No countries match \"{0}\".",
            "没有匹配 \"{0}\" 的国家。");
        table.Add("Datamoll.RetryingOrder",
            "Повторная попытка того же заказа с Datamoll...",
            "Retrying the same order with Datamoll...",
            "正在使用 Datamoll 重试同一订单...");
        table.Add("Datamoll.PurchasingWaiting",
            "Покупка и ожидание доставки Datamoll...",
            "Purchasing and waiting for Datamoll delivery...",
            "正在购买并等待 Datamoll 交付...");
        table.Add("Datamoll.StatusPurchasing", "Покупка", "Purchasing", "购买中");
        table.Add("Datamoll.StatusRecovered", "Восстановлено", "Recovered", "已恢复");
        table.Add("Datamoll.StatusFailed", "Ошибка", "Failed", "失败");
        table.Add("Datamoll.RecoveredImportedFormat",
            "Восстановлено и импортировано: {0} сессия(и), {1} tdata.",
            "Recovered and imported: {0} session, {1} tdata.",
            "已恢复并导入：{0} 个会话，{1} 个 tdata。");
        table.Add("Datamoll.DownloadedImportedFormat",
            "Скачано и импортировано: {0} сессия(и), {1} tdata.",
            "Downloaded and imported: {0} session, {1} tdata.",
            "已下载并导入：{0} 个会话，{1} 个 tdata。");
        table.Add("Datamoll.OrderAddedFormat",
            "Заказ {0}: {1} аккаунт(ов) добавлено в существующее хранилище",
            "Order {0}: {1} account(s) added to existing storage",
            "订单 {0}：已将 {1} 个账户添加到现有存储");
        table.Add("Datamoll.SkippedExistingSuffixFormat",
            ", {0} уже существовало.",
            ", {0} already existed.",
            "，其中 {0} 个已存在。");
        table.Add("Datamoll.SameOrderWillBeReused",
            "Тот же ID заказа будет использован повторно при повторном нажатии «Купить».",
            "The same order ID will be reused if you press Purchase again.",
            "如果您再次点击购买，将重复使用相同的订单 ID。");
    }
}
