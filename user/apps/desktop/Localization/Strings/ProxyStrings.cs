namespace TgPoolLauncher.Localization.Strings;

internal static class ProxyStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Proxy.CheckAll", "Проверить прокси", "Check proxies", "检查代理");
        table.Add("Proxy.DeleteAll", "Удалить все", "Delete all", "全部删除");
        table.Add("Proxy.DeleteBad", "Удалить плохие", "Delete bad", "删除无效代理");
        table.Add("Proxy.DeleteAllConfirm", "Удалить все сохраненные прокси?", "Delete all saved proxies?", "删除所有已保存的代理？");
        table.Add("Proxy.Timeout", "Таймаут (с)", "Timeout (s)", "超时（秒）");
        table.Add("Proxy.Retries", "Повторы", "Retries", "重试");
        table.Add("Proxy.ColLogin", "Логин", "Login", "用户名");
        table.Add("Proxy.ColPassword", "Пароль", "Password", "密码");
        table.Add("Proxy.ColVersion", "Версия", "Version", "版本");
        table.Add("Proxy.ColResponse", "Отклик", "Response", "响应");
        table.Add("Proxy.ColStatus", "Статус", "Status", "状态");
        table.Add("Proxy.ColActions", "Действия", "Actions", "操作");
        table.Add("Proxy.CheckOne", "Проверить", "Check", "检查");
        table.Add("Proxy.DeleteOne", "Удалить", "Delete", "删除");
        table.Add("Proxy.AddSection", "ДОБАВИТЬ ПРОКСИ", "ADD PROXIES", "添加代理");
        table.Add("Proxy.Protocol", "Протокол", "Protocol", "协议");
        table.Add("Proxy.ProxyList", "Список прокси", "Proxy list", "代理列表");
        table.Add("Proxy.AddFormat", "Формат: ip:port или ip:port:login:password", "Format: ip:port or ip:port:login:password", "格式：ip:port 或 ip:port:login:password");
        table.Add("Proxy.AddButton", "Добавить", "Add", "添加");

        table.Add("Proxy.SectionList", "СПИСОК ПРОКСИ", "PROXY LIST", "代理列表");
        table.Add("Proxy.ListHint", "По одному на строку: host:port[:type[:user:pass]]",
            "One per line: host:port[:type[:user:pass]]", "每行一个：host:port[:type[:user:pass]]");
        table.Add("Proxy.CheckButton", "Проверить", "Check", "检测");
        table.Add("Proxy.SectionResults", "РЕЗУЛЬТАТЫ ПРОВЕРКИ", "CHECK RESULTS", "检测结果");
        table.Add("Proxy.ColHost", "Хост", "Host", "主机");
        table.Add("Proxy.ColPort", "Порт", "Port", "端口");
        table.Add("Proxy.ColType", "Тип", "Type", "类型");
        table.Add("Proxy.ColActive", "Активен", "Active", "是否有效");
        table.Add("Proxy.ColLatency", "Пинг (мс)", "Ping (ms)", "延迟（毫秒）");
        table.Add("Proxy.ColGeo", "Гео", "Geo", "地区");
        table.Add("Proxy.ColError", "Ошибка", "Error", "错误");
        table.Add("Proxy.EmptyListError",
            "Список прокси пуст или не распознан (формат: host:port[:type[:user:pass]]).",
            "Proxy list is empty or unrecognized (format: host:port[:type[:user:pass]]).",
            "代理列表为空或格式无法识别（格式：host:port[:type[:user:pass]]）。");

        table.Add("Rotation.ModeLabel", "Режим работы", "Mode", "工作模式");
        table.Add("Rotation.ModeRotating", "Ротационные прокси", "Rotating proxies", "轮换代理");
        table.Add("Rotation.ModeSticky", "Липкие прокси", "Sticky proxies", "粘性代理");
        table.Add("Rotation.ProtocolLabel", "Протокол", "Protocol", "协议");
        table.Add("Rotation.ProtocolHttp", "HTTP", "HTTP", "HTTP");
        table.Add("Rotation.ProtocolSocks5", "SOCKS 5", "SOCKS 5", "SOCKS 5");
        table.Add("Rotation.ProxyListLabel", "Ротационные прокси", "Rotating proxies", "轮换代理");
        table.Add("Rotation.StickyProxyListLabel", "Липкие прокси", "Sticky proxies", "粘性代理");
        table.Add("Rotation.RequestCountLabel", "Количество запросов", "Number of requests", "请求数量");
        table.Add("Rotation.UniqueLabel", "Уникальных", "Unique", "唯一");
        table.Add("Rotation.DuplicateLabel", "Повторяющихся", "Duplicate", "重复");
        table.Add("Rotation.DuplicatesLabel", "Повторяющихся", "Duplicates", "重复");
        table.Add("Rotation.ErrorsLabel", "Ошибки соединения", "Connection errors", "连接错误");
        table.Add("Rotation.StartTooltip",
            "Скоро — тест ротации прокси ещё не реализован в бэкенде (нужен реальный запрос через " +
            "прокси к IP-сервису, сейчас есть только проверка соединения)",
            "Soon — proxy rotation testing isn't implemented in the backend yet (it needs a real " +
            "request through the proxy to an IP service; currently only a connection check exists)",
            "即将推出——后端尚未实现代理轮换测试（需要通过代理向 IP 服务发起真实请求，目前只有连接检测）");
        table.Add("Rotation.RunButton", "Запустить", "Run", "运行");
        table.Add("Rotation.ImportantHeader", "ВАЖНАЯ ИНФОРМАЦИЯ", "IMPORTANT INFORMATION", "重要信息");
        table.Add("Rotation.ImportantUnique",
            "Пул оценивается по количеству уникальных IP, дублей и ошибок соединения.",
            "The pool is evaluated by unique exit IPs, duplicates, and connection errors.",
            "代理池按唯一出口 IP、重复项和连接错误进行评估。");
        table.Add("Rotation.ImportantSticky",
            "Для sticky-прокси одна строка в идеале должна давать один уникальный IP.",
            "For sticky proxies, each line should ideally resolve to one unique IP.",
            "对于粘性代理，理想情况下每一行都应解析为一个唯一 IP。");
        table.Add("Rotation.ImportantBackend",
            "Проверка отправляет реальные запросы через прокси к IP-сервису и считает exit IP.",
            "The checker sends real requests through each proxy to an IP service and counts exit IPs.",
            "检查器会通过每个代理向 IP 服务发送真实请求并统计出口 IP。");
        table.Add("Rotation.RequestCountError",
            "Укажи количество запросов больше 0.",
            "Enter a number of requests greater than 0.",
            "请输入大于 0 的请求数量。");
    }
}
