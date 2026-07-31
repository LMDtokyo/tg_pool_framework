namespace TgPoolLauncher.Localization.Strings;

/// <summary>
/// Content for the Manual tab (Views/ManualView.xaml, ViewModels/ManualViewModel.cs) --
/// an in-app knowledge base covering every feature. Kept as one long localized
/// string per category (same pattern App.BackendFailedMessage already uses for
/// multi-line text) rather than a separate content format, so it re-renders on
/// a language switch exactly like every other string in the app.
/// </summary>
internal static class ManualStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("Manual.NavHeader", "Разделы", "Sections", "章节");
        table.Add("Manual.SearchPlaceholder", "Поиск по руководству...", "Search the manual...", "搜索手册...");
        table.Add("Manual.NoResults", "Ничего не найдено.", "Nothing found.", "未找到相关内容。");

        // ------------------------------------------------------------------
        // 1. Getting started
        // ------------------------------------------------------------------
        table.Add("Manual.GettingStarted.Title", "Начало работы", "Getting Started", "快速入门");
        table.Add("Manual.GettingStarted.Body",
            "Программа ставится через установщик и не требует прав администратора — можно выбрать «установить только для себя», тогда всё хранится в папке пользователя.\n\n" +
            "При первом запуске (и при каждом следующем, если лицензия ещё не активна) появляется отдельное консольное окно активации — TgPoolActivator.exe. Введите ключ подписки, полученный при покупке. После успешной активации окно закрывается само, и открывается основное окно программы.\n\n" +
            "При каждом старте программа поднимает свой внутренний бэкенд как фоновый процесс (виден в диспетчере задач как python.exe) — это нормально, не закрывайте его вручную. Программа сама останавливает его при выходе. Если бэкенд не поднялся за ~20 секунд, появится окно с ошибкой — обычно это значит, что на компьютере не установлен Python или не поставлены зависимости (см. инструкцию установщика).\n\n" +
            "Вся рабочая информация — аккаунты, прокси, экспорты, логи — хранится в папке Data рядом с программой. Подробнее — в разделе «Структура папки Data».\n\n" +
            "Язык интерфейса переключается кнопками в правом верхнем углу окна (RU / EN / ZH) — переключение мгновенное, без перезапуска.",
            "The app installs without admin rights — you can choose \"install for me only\" and everything stays under your user profile.\n\n" +
            "On first launch (and on any launch before the license is active) a separate console window appears — TgPoolActivator.exe. Enter the subscription key you received at purchase. Once activated it closes itself and the main window opens.\n\n" +
            "On every launch the app starts its own backend as a background process (visible in Task Manager as python.exe) — this is normal, don't close it manually, the app stops it on exit. If the backend doesn't come up within ~20 seconds you'll see an error dialog — usually it means Python or its dependencies aren't installed on this machine (see the installer's instructions).\n\n" +
            "Everything the app works with — accounts, proxies, exports, logs — lives under a Data folder next to the app. See \"Data Folder Layout\" for details.\n\n" +
            "The interface language switches instantly via the RU / EN / ZH buttons in the top-right corner, no restart needed.",
            "本软件通过安装程序安装，无需管理员权限——可以选择“仅为我安装”，这样所有数据都保存在用户目录下。\n\n" +
            "首次启动时（以及许可证尚未激活时的每次启动）会弹出一个独立的控制台激活窗口——TgPoolActivator.exe。输入购买时获得的订阅密钥。激活成功后该窗口会自动关闭，随后打开主窗口。\n\n" +
            "每次启动时，程序都会把自己的后端作为后台进程启动（在任务管理器中显示为 python.exe）——这是正常现象，请不要手动关闭它，程序退出时会自动停止后端。如果大约 20 秒内后端仍未就绪，会弹出错误窗口——通常意味着这台电脑没有安装 Python 或缺少依赖（参见安装程序的说明）。\n\n" +
            "所有工作数据——账户、代理、导出文件、日志——都保存在程序旁边的 Data 文件夹中。详见“Data 文件夹结构”一节。\n\n" +
            "界面语言可通过窗口右上角的 RU / EN / ZH 按钮即时切换，无需重启。");

        // ------------------------------------------------------------------
        // 2. Data folder layout
        // ------------------------------------------------------------------
        table.Add("Manual.DataFolder.Title", "Структура папки Data", "Data Folder Layout", "Data 文件夹结构");
        table.Add("Manual.DataFolder.Body",
            "Data\\Accounts — основной пул: .session-файлы аккаунтов и их .json-спутники (или голые .session, если настроены api_id/api_hash по умолчанию — см. раздел «Аккаунты»).\n\n" +
            "Data\\AccountsSpare — запасной пул (те же форматы), используется отдельно от основного там, где это предусмотрено функцией.\n\n" +
            "Data\\Tdata — папки Telegram Desktop (tdata) для автоконвертации в сессии.\n\n" +
            "Data\\Sessions — куда конвертер Tdata→Session кладёт результат по умолчанию.\n\n" +
            "Data\\TdataExports — куда конвертер Session→Tdata кладёт результат по умолчанию.\n\n" +
            "Data\\Proxies — база уже сохранённых прокси (вкладка «Прокси»).\n\n" +
            "Data\\Exports — результаты рассылок, накрутки, проверки номеров, парсинга и т.д. (xlsx/txt).\n\n" +
            "Data\\Fingerprints — каталог отпечатков устройств (telegram_devices.xlsx по умолчанию).\n\n" +
            "Data\\JsonGenerator — куда JSON-генератор кладёт сгенерированные .json-спутники.\n\n" +
            "Data\\DatamollReceipts — чеки покупок готовых аккаунтов через Datamoll.\n\n" +
            "Data\\Tools — установщики рекомендованных вспомогательных программ (скачиваются с Дашборда).\n\n" +
            "Data\\Logs и Data\\Crashes — технические логи бэкенда и отчёты о падениях программы; пригодятся, если понадобится помощь техподдержки.",
            "Data\\Accounts — the main pool: account .session files with their .json companions (or bare .session files if a default api_id/api_hash is configured — see \"Accounts\").\n\n" +
            "Data\\AccountsSpare — a secondary pool (same formats), used separately from the main one where a feature calls for it.\n\n" +
            "Data\\Tdata — Telegram Desktop (tdata) folders for auto-conversion into sessions.\n\n" +
            "Data\\Sessions — default output of the Tdata→Session converter.\n\n" +
            "Data\\TdataExports — default output of the Session→Tdata converter.\n\n" +
            "Data\\Proxies — the saved-proxy database (Proxy tab).\n\n" +
            "Data\\Exports — results from sending, engagement, number checking, parsing, etc. (xlsx/txt).\n\n" +
            "Data\\Fingerprints — the device fingerprint catalog (telegram_devices.xlsx by default).\n\n" +
            "Data\\JsonGenerator — where the JSON Generator writes generated .json companions.\n\n" +
            "Data\\DatamollReceipts — purchase receipts from buying ready-made accounts via Datamoll.\n\n" +
            "Data\\Tools — installers for recommended helper apps (downloaded from the Dashboard).\n\n" +
            "Data\\Logs and Data\\Crashes — backend technical logs and crash reports; useful if you ever need support.",
            "Data\\Accounts — 主账户池：账户的 .session 文件及其 .json 配套文件（如果配置了默认 api_id/api_hash，也可以是裸 .session 文件——见“账户”一节）。\n\n" +
            "Data\\AccountsSpare — 备用账户池（格式相同），在某些功能中与主账户池分开使用。\n\n" +
            "Data\\Tdata — Telegram Desktop（tdata）文件夹，用于自动转换为账户会话。\n\n" +
            "Data\\Sessions — Tdata→Session 转换工具的默认输出位置。\n\n" +
            "Data\\TdataExports — Session→Tdata 转换工具的默认输出位置。\n\n" +
            "Data\\Proxies — 已保存代理的数据库（“代理”页面）。\n\n" +
            "Data\\Exports — 群发、互动增长、号码检测、数据抓取等功能的结果文件（xlsx/txt）。\n\n" +
            "Data\\Fingerprints — 设备指纹目录（默认 telegram_devices.xlsx）。\n\n" +
            "Data\\JsonGenerator — JSON 生成器写入生成的 .json 配套文件的位置。\n\n" +
            "Data\\DatamollReceipts — 通过 Datamoll 购买成品账户的收据。\n\n" +
            "Data\\Tools — 从仪表盘下载的推荐辅助工具安装包。\n\n" +
            "Data\\Logs 和 Data\\Crashes — 后端技术日志和程序崩溃报告，需要技术支持时会用到。");

        // ------------------------------------------------------------------
        // 3. Accounts
        // ------------------------------------------------------------------
        table.Add("Manual.Accounts.Title", "Аккаунты: добавление и форматы", "Accounts: Adding & Formats", "账户：添加与格式");
        table.Add("Manual.Accounts.Body",
            "Программа принимает три формата аккаунтов, и все три можно просто скопировать в Data\\Accounts (или Data\\AccountsSpare):\n\n" +
            "• .session + .json — пара файлов с одинаковым именем. В .json указываются app_id (или api_id), app_hash (или api_hash), phone и, опционально, отпечаток устройства (device/system/app_version и т.д. — см. раздел «Отпечатки устройств»). Оба варианта имён ключей (app_id/api_id) распознаются одинаково.\n\n" +
            "• Голый .session без .json — сработает, только если на вкладке «Аккаунты» заданы api_id и api_hash по умолчанию (раскрывающийся блок «Api_id/api_hash по умолчанию»). Программа сама подберёт этому аккаунту уникальный отпечаток устройства из каталога и сохранит рядом .json — повторный запуск будет использовать уже сохранённый отпечаток. Без заданных значений по умолчанию такой файл будет пропущен с пометкой в результатах скана.\n\n" +
            "• Папка Tdata (Telegram Desktop) — положите в Data\\Tdata, программа сама найдёт и сконвертирует.\n\n" +
            "Подхват новых файлов происходит автоматически: фоновая проверка сканирует папки каждые ~20 секунд, а также при каждом открытии или обновлении вкладки «Аккаунты». Когда находятся новые аккаунты, на Дашборде появляется баннер с количеством загруженных и (если были) неудачных файлов с указанием причины — например, отсутствие .json и не заданные api_id/api_hash по умолчанию, или файл в формате, который программа не распознала.\n\n" +
            "Купленные на стороне базы аккаунтов через маркетплейс Datamoll импортируются автоматически прямо из программы — см. раздел «Datamoll».",
            "The app accepts three account formats, and all three can simply be copied into Data\\Accounts (or Data\\AccountsSpare):\n\n" +
            "• .session + .json — a matching pair of files. The .json specifies app_id (or api_id), app_hash (or api_hash), phone, and optionally a device fingerprint (device/system/app_version, etc. — see \"Device Fingerprints\"). Both key-name spellings (app_id/api_id) are recognized equally.\n\n" +
            "• A bare .session with no .json — works only if a default api_id/api_hash is set on the Accounts tab (the \"Default api_id/api_hash\" expander). The app assigns it a unique device fingerprint from the catalog and saves a matching .json next to it — the next load reuses that same fingerprint. Without a configured default, such a file is skipped and flagged in the scan results.\n\n" +
            "• A Telegram Desktop (Tdata) folder — drop it into Data\\Tdata and the app finds and converts it automatically.\n\n" +
            "New files are picked up automatically: a background sweep scans the folders roughly every 20 seconds, and again every time you open or refresh the Accounts tab. When new accounts are found, a Dashboard banner shows how many loaded and how many (if any) failed, with the reason — e.g. no .json and no default api_id/api_hash, or a file format the app didn't recognize.\n\n" +
            "Account bases bought through the Datamoll marketplace are imported automatically right from the app — see \"Datamoll\".",
            "程序支持三种账户格式，这三种都可以直接复制到 Data\\Accounts（或 Data\\AccountsSpare）中：\n\n" +
            "• .session + .json ——一对同名文件。.json 中需要填写 app_id（或 api_id）、app_hash（或 api_hash）、phone，以及可选的设备指纹（device/system/app_version 等——见“设备指纹”一节）。两种字段命名方式（app_id/api_id）都能识别。\n\n" +
            "• 没有 .json 的裸 .session 文件——仅当在“账户”页面设置了默认 api_id/api_hash（“默认 api_id/api_hash”展开区）时才能生效。程序会从指纹目录中为该账户分配一个唯一的设备指纹，并在旁边保存对应的 .json 文件——下次加载会复用该指纹。如果未设置默认值，此类文件会被跳过并在扫描结果中标注原因。\n\n" +
            "• Telegram Desktop（Tdata）文件夹——放入 Data\\Tdata，程序会自动发现并转换。\n\n" +
            "新文件会被自动识别：后台每约 20 秒扫描一次这些文件夹，打开或刷新“账户”页面时也会扫描。发现新账户时，仪表盘会显示一个提示条，说明成功加载和（如有）失败的数量及原因——例如缺少 .json 且未设置默认 api_id/api_hash，或程序无法识别的文件格式。\n\n" +
            "通过 Datamoll 市场购买的成品账户库会由程序自动导入——见“Datamoll”一节。");

        // ------------------------------------------------------------------
        // 4. Fingerprints
        // ------------------------------------------------------------------
        table.Add("Manual.Fingerprints.Title", "Отпечатки устройств", "Device Fingerprints", "设备指纹");
        table.Add("Manual.Fingerprints.Body",
            "«Отпечаток устройства» — это набор данных (модель телефона, версия системы, версия приложения Telegram и т.д.), которые клиент сообщает серверам Telegram при каждом подключении. Если у двух разных аккаунтов пула одинаковый отпечаток, Telegram может расценить это как один и тот же взломанный/автоматизированный клиент, управляющий несколькими аккаунтами — это повышает риск банов.\n\n" +
            "Программа хранит список возможных отпечатков в файле-каталоге (по умолчанию Data\\Fingerprints\\telegram_devices.xlsx, также поддерживаются CSV, JSON, XLSM). Каждому новому аккаунту — при регистрации через встроенную SMS-активацию или при добавлении голого .session с заданными api_id/api_hash по умолчанию — автоматически подбирается отпечаток, ещё не использованный другими аккаунтами пула. Выбранный отпечаток сохраняется вместе с аккаунтом и больше не меняется.\n\n" +
            "Инструмент «JSON-генератор» позволяет вручную проставить отпечатки пачке уже существующих .session-файлов, у которых нет .json — выбираете каталог отпечатков, папку с сессиями и папку для результата; программа не трогает исходные .session, только создаёт .json рядом.\n\n" +
            "Если каталог отпечатков не задан или закончился (все варианты уже заняты), программа предупредит в логах и всё равно назначит отпечаток, но уже с повтором — по возможности держите каталог достаточно большим для размера вашего пула.",
            "A \"device fingerprint\" is the set of data (phone model, system version, Telegram app version, etc.) a client reports to Telegram's servers on every connection. If two different accounts in the pool report the identical fingerprint, Telegram can treat that as one compromised/automated client controlling multiple accounts — raising ban risk.\n\n" +
            "The app keeps a catalog of possible fingerprints in a file (Data\\Fingerprints\\telegram_devices.xlsx by default; CSV, JSON, and XLSM are also supported). Every new account — whether registered via the built-in SMS activation or added as a bare .session with a default api_id/api_hash configured — automatically gets a fingerprint not already used by another account in the pool. The chosen fingerprint is saved with the account and never changes afterward.\n\n" +
            "The \"JSON Generator\" tool lets you manually stamp fingerprints onto a batch of existing .session files that have no .json — pick the fingerprint catalog, the sessions folder, and an output folder; the app never touches the source .session files, it only creates matching .json files.\n\n" +
            "If no catalog is configured, or every entry is already in use, the app logs a warning and still assigns a fingerprint, accepting a repeat — keep the catalog large enough for your pool size.",
            "“设备指纹”是客户端每次连接 Telegram 服务器时上报的一组数据（手机型号、系统版本、Telegram 应用版本等）。如果账户池中两个不同的账户使用完全相同的指纹，Telegram 可能会将其视为同一个被劫持/自动化的客户端在操控多个账户——从而提高被封风险。\n\n" +
            "程序在一个目录文件中维护可用指纹列表（默认 Data\\Fingerprints\\telegram_devices.xlsx，同时支持 CSV、JSON、XLSM 格式）。每个新账户——无论是通过内置短信激活注册的，还是以配置了默认 api_id/api_hash 的裸 .session 文件添加的——都会自动分配一个账户池中尚未被占用的指纹。所选指纹会与账户一起保存，之后不再更改。\n\n" +
            "“JSON 生成器”工具可以为一批没有 .json 文件的现有 .session 文件手动打上指纹——选择指纹目录、会话文件夹和输出文件夹即可；程序不会修改原始 .session 文件，只会生成对应的 .json 文件。\n\n" +
            "如果未配置指纹目录，或所有条目都已被占用，程序会在日志中给出警告，但仍会分配一个指纹（可能重复）——请确保目录规模足以覆盖你的账户池。");

        // ------------------------------------------------------------------
        // 5. Proxies
        // ------------------------------------------------------------------
        table.Add("Manual.Proxies.Title", "Прокси", "Proxies", "代理");
        table.Add("Manual.Proxies.Body",
            "Вкладка «Прокси» — это хранимый пул: список прокси, сохранённых в базе программы. Здесь их можно добавлять (в том числе списком), проверять (весь список или один по кнопке, с настраиваемым таймаутом и числом попыток) и удалять — по одному, только нерабочие или все сразу. Именно из этого пула программа берёт прокси для аккаунтов.\n\n" +
            "Вкладка «Чекер пула прокси» — это одноразовая проверка, без сохранения. Два режима: «Rotating» — вставляете один адрес ротационного шлюза и указываете, сколько запросов через него сделать; «Sticky» — вставляете список отдельных прокси построчно (ip:port:логин:пароль). Программа реально пропускает через каждый запросы и показывает число уникальных исходящих IP, дубликатов и ошибок соединения — удобно, чтобы проверить прокси-провайдера, прежде чем покупать/подключать его в основной пул.\n\n" +
            "Переключатель «Запретить отправку с непрокси-аккаунтов» (require proxy) есть на всех задачах рассылки, накрутки, сторис и инвайта и по умолчанию включён: если у выбранного для запуска аккаунта нет прокси, задача не запустится, а не тихо подключится через IP этого компьютера. Там же программа не даст запустить задачу, если несколько выбранных аккаунтов используют один и тот же прокси — Telegram может связать их между собой по общему выходному IP.",
            "The Proxy Check tab is a stored pool: proxies saved in the app's own database. Here you can add them (including in bulk), check them (the whole list or one at a time, with configurable timeout and retry count), and delete them — one at a time, only the broken ones, or all at once. This is the pool the app actually draws proxies from for accounts.\n\n" +
            "The Proxy Pool Checker tab is a one-off test with nothing saved. Two modes: \"Rotating\" — paste one rotating-gateway address and set how many requests to send through it; \"Sticky\" — paste a list of individual proxies, one per line (ip:port:login:password). The app fires real requests through each and reports unique outbound IPs, duplicates, and connection errors — useful for vetting a proxy provider before committing it to the main pool.\n\n" +
            "The \"Require proxy\" toggle exists on every sending, engagement, stories, and invite job and is on by default: if a selected account has no proxy, the job refuses to start instead of silently connecting through this computer's own IP. The same check also blocks starting a job if several selected accounts share the exact same proxy — Telegram can correlate them through a shared exit IP.",
            "“代理检测”页面是一个持久化的代理池：保存在程序数据库中的代理列表。可以在这里添加代理（支持批量添加）、检测（整批或单个，可设置超时和重试次数）、删除（单个、仅失效的或全部）。程序实际就是从这个池中为账户分配代理的。\n\n" +
            "“代理池检查器”页面是一次性检测，不做任何保存。两种模式：“Rotating（轮换）”——粘贴一个轮换网关地址，并设置通过它发送多少请求；“Sticky（固定）”——逐行粘贴单个代理列表（ip:port:用户名:密码）。程序会真实地通过每个代理发送请求，统计唯一出口 IP 数、重复数和连接错误数——适合在把某个代理供应商正式接入主账户池之前先做验证。\n\n" +
            "“要求使用代理”开关存在于所有群发、互动增长、快拍和邀请任务中，默认开启：如果所选账户没有代理，任务会拒绝启动，而不是悄悄通过本机 IP 连接。同一个检查还会在多个所选账户使用同一个代理时阻止任务启动——Telegram 可能通过相同的出口 IP 将它们关联起来。");

        // ------------------------------------------------------------------
        // 6. Safety
        // ------------------------------------------------------------------
        table.Add("Manual.Safety.Title", "Защита от банов", "Ban Protection", "防封号保护");
        table.Add("Manual.Safety.Body",
            "У программы есть несколько встроенных механизмов защиты пула, часть из них включена по умолчанию, часть — опциональные настройки для продвинутых пользователей (задаются при установке/настройке бэкенда):\n\n" +
            "• Требование прокси и запрет общих прокси — включены по умолчанию на всех задачах (см. раздел «Прокси»).\n\n" +
            "• Прогрев новых аккаунтов (warmup) — если включён, свежезарегистрированные или недавно добавленные аккаунты автоматически работают медленнее и с более низким дневным лимитом действий первые несколько дней, постепенно выходя на полную скорость. Это резко снижает риск раннего бана у аккаунта, который ещё не «отлежался».\n\n" +
            "• Авто-возврат в пул после ограничения (cooldown) — если включён, аккаунт, получивший спамблок/заморозку/флуд-лимит, автоматически перепроверяется после истечения срока ограничения и возвращается в работу сам, без ручного вмешательства.\n\n" +
            "• Автостоп по банам/спамблокам/флудвейтам — почти во всех задачах можно задать порог (например, «остановить после 3 банов»), и задача сама остановится, не давая проблеме нарастать на весь пул.\n\n" +
            "• Дневные лимиты по типу действия — у накрутки и сторис есть безопасные значения по умолчанию (например, не более 1–2 просмотров сторис в день на аккаунт — это ограничение самого Telegram, не программы).\n\n" +
            "Если у вас есть сомнения по конкретной настройке — уточните у того, кто устанавливал и настраивал программу: часть параметров задаётся один раз при разворачивании и не видна напрямую в интерфейсе.",
            "The app has several built-in pool-protection mechanisms — some are on by default, others are optional advanced settings configured when the backend is deployed:\n\n" +
            "• Require-proxy and no-shared-proxy — on by default for every job (see \"Proxies\").\n\n" +
            "• New-account warmup — when enabled, freshly registered or recently added accounts automatically run slower and with a lower daily action cap for the first several days, ramping up gradually to full speed. This sharply cuts the risk of an early ban on an account that hasn't \"aged\" yet.\n\n" +
            "• Auto-return after cooldown — when enabled, an account that got a spam-block/freeze/flood-limit is automatically re-checked once its restriction expires and returns to work on its own, no manual step needed.\n\n" +
            "• Auto-stop on bans/spam-blocks/flood-waits — nearly every job lets you set a threshold (e.g. \"stop after 3 bans\") so a problem can't spread across the whole pool unattended.\n\n" +
            "• Per-action daily caps — engagement and stories ship with safe defaults (e.g. no more than 1-2 story views per account per day — that's Telegram's own limit, not the app's).\n\n" +
            "If you're unsure about a specific setting, ask whoever installed and configured the app — some parameters are set once at deployment time and aren't directly exposed in the UI.",
            "程序内置了多种账户池保护机制，部分默认开启，部分是需要在部署后端时配置的高级选项：\n\n" +
            "• 要求使用代理、禁止共用代理——所有任务默认开启（见“代理”一节）。\n\n" +
            "• 新账户预热（warmup）——启用后，刚注册或刚添加的账户在最初几天会自动以更慢的速度、更低的每日操作上限运行，逐步提升到正常速度。这能大幅降低“还未养熟”的账户过早被封的风险。\n\n" +
            "• 限制解除后自动恢复（cooldown）——启用后，被限流/冻结/触发洪水限制的账户会在限制到期后自动重新检测，并自行恢复工作，无需人工干预。\n\n" +
            "• 按封号/限流/洪水限制自动停止——几乎所有任务都可以设置阈值（例如“出现 3 次封号后停止”），从而避免问题扩散到整个账户池。\n\n" +
            "• 按操作类型的每日上限——互动增长和快拍功能自带安全的默认值（例如每个账户每天最多查看 1-2 次快拍——这是 Telegram 自身的限制，并非程序设定）。\n\n" +
            "如果对某项具体设置有疑问，请咨询安装和配置该程序的人员——部分参数是在部署时一次性设定的，界面中不直接可见。");

        // ------------------------------------------------------------------
        // 7. Auto-register
        // ------------------------------------------------------------------
        table.Add("Manual.AutoRegister.Title", "Авто-регистрация (SMS-активация)", "Auto-Register (SMS Activation)", "自动注册（短信激活）");
        table.Add("Manual.AutoRegister.Body",
            "Раздел «Авто-регистрация» в боковом меню объединяет способы получить новые Telegram-аккаунты. В группе основных страниц: hero-sms, SMSpool, GrizzlySMS — три сервиса аренды номеров, работающие одинаково; Datamoll — покупка уже готовых аккаунтов (отдельный раздел); Universal (activate) — заготовка под будущий универсальный экран, сейчас не работает (кнопки запуска отключены).\n\n" +
            "Для hero-sms / SMSpool / GrizzlySMS нужен API-ключ соответствующего сервиса (получается на его сайте, вводится в программе и не сохраняется на диске). Дальше выбираете страну, оператора, стартовую и максимальную цену за номер (программа поднимается до максимума, только если по стартовой номеров не осталось), сколько аккаунтов нужно получить, сколько номеров держать «в работе» одновременно (1–10) и таймаут ожидания SMS. Программа сама заменяет неудачные попытки, пока не наберёт нужное количество, и покажет по каждой попытке номер, оператора, стоимость, стадию и код. Если Telegram запросит облачный пароль (2FA), появится отдельная панель для его ввода.\n\n" +
            "В группе «Отправка SMS» — это на самом деле рассылки и связанные с ними инструменты, а не SMS-активация: Sending SMS by ID, Send by numbers, Number checker, Scheduled campaigns (см. соответствующие разделы руководства).\n\n" +
            "В группе «Инвайт» — Invite by number (см. раздел «Плановые кампании, инвайт и проверка номеров»).",
            "The \"Auto Register\" section in the side menu groups together the ways to get new Telegram accounts. In the main pages group: hero-sms, SMSpool, GrizzlySMS — three number-rental services that work identically; Datamoll — buying already-made accounts (its own section below); Universal (activate) — a placeholder for a future generic screen, currently non-functional (its Start button is disabled).\n\n" +
            "hero-sms / SMSpool / GrizzlySMS each need an API key from that service (obtained on its website, entered in the app, never written to disk). You then pick a country, operator, a starting and a ceiling price per number (the app only climbs to the ceiling once the starting tier is sold out), how many accounts you want, how many numbers to keep \"in flight\" at once (1-10), and an SMS wait timeout. The app automatically replaces failed attempts until it reaches the target, showing phone/operator/cost/stage/code per attempt. If Telegram asks for a cloud password (2FA) during registration, a separate panel appears for entering it.\n\n" +
            "The \"Sending SMS\" group is actually broadcasting and its related tools, not SMS activation: Sending SMS by ID, Send by numbers, Number checker, Scheduled campaigns (see their own sections below).\n\n" +
            "The \"Invite\" group holds Invite by number (see \"Scheduling, Invites & Number Checking\").",
            "侧边栏中的“自动注册”分组汇集了获取新 Telegram 账户的各种方式。主页面组包括：hero-sms、SMSpool、GrizzlySMS——三个工作方式相同的号码租用服务；Datamoll——购买成品账户（单独一节介绍）；Universal (activate)——为未来通用页面预留的占位界面，目前尚不可用（启动按钮被禁用）。\n\n" +
            "使用 hero-sms / SMSpool / GrizzlySMS 需要该服务的 API 密钥（在其官网获取，输入到程序中，不会写入磁盘）。之后选择国家、运营商、起始价格和上限价格（只有起始档位号码售罄时程序才会提高到上限价格）、需要获取的账户数量、同时保持“进行中”的号码数（1-10个），以及短信等待超时时间。程序会自动替换失败的尝试，直到达到目标数量，并显示每次尝试的号码、运营商、费用、阶段和验证码。如果 Telegram 在注册过程中要求云密码（两步验证），会弹出单独的输入面板。\n\n" +
            "“发送短信”分组实际上是群发功能及其相关工具，而不是短信激活：Sending SMS by ID、Send by numbers、Number checker、Scheduled campaigns（见下方对应章节）。\n\n" +
            "“邀请”分组包含 Invite by number（见“计划任务、邀请与号码检测”一节）。");

        // ------------------------------------------------------------------
        // 8. Datamoll
        // ------------------------------------------------------------------
        table.Add("Manual.Datamoll.Title", "Datamoll — покупка готовых аккаунтов", "Datamoll — Buying Ready Accounts", "Datamoll——购买成品账户");
        table.Add("Manual.Datamoll.Body",
            "Datamoll — маркетплейс уже зарегистрированных Telegram-аккаунтов (datamollcore.com). В отличие от авто-регистрации, номер телефона не арендуется — аккаунт покупается готовым.\n\n" +
            "Нужны API-ключ и API-секрет от личного кабинета Datamoll. После ввода программа загружает актуальный каталог в наличии (можно фильтровать поиском по стране), для каждой позиции видно страну, возраст аккаунта, цену за штуку, остаток на складе и мин/макс размер заказа. Указываете количество и нажимаете «Купить».\n\n" +
            "Дальше всё происходит автоматически: программа оформляет заказ, сохраняет чек в Data\\DatamollReceipts, скачивает доставленный архив с аккаунтами, безопасно его распаковывает и раскладывает содержимое по нужным папкам — .session+.json пары в Data\\Accounts, папки с tdata в Data\\Tdata (уже существующие файлы с тем же именем не перезаписываются). После этого программа сама пересканирует хранилище аккаунтов, и новые аккаунты сразу становятся видны на вкладке «Аккаунты» — вручную ничего переносить не нужно. По итогам покупки показывается сводка: сколько доставлено, сколько импортировано как session/tdata, сколько пропущено и сколько всего новых аккаунтов зарегистрировано в программе.",
            "Datamoll is a marketplace of already-registered Telegram accounts (datamollcore.com). Unlike auto-registration, no phone number is rented — you buy a finished account outright.\n\n" +
            "You need an API key and API secret from your Datamoll account. Once entered, the app loads the live in-stock catalog (filterable by country search); each listing shows country, account age, unit price, remaining stock, and min/max order size. Set a quantity and click Purchase.\n\n" +
            "Everything after that is automatic: the app places the order, saves a receipt under Data\\DatamollReceipts, downloads the delivered account archive, safely extracts it, and sorts the contents into the right folders — .session+.json pairs into Data\\Accounts, tdata folders into Data\\Tdata (files that already exist under the same name are not overwritten). The app then rescans account storage itself, so the new accounts show up on the Accounts tab immediately — nothing to move by hand. The purchase summary reports how many were delivered, how many imported as sessions vs. tdata, how many were skipped, and how many new accounts were registered in the app in total.",
            "Datamoll 是一个已注册 Telegram 账户的交易市场（datamollcore.com）。与自动注册不同，这里不租用手机号，而是直接购买成品账户。\n\n" +
            "需要在 Datamoll 个人中心获取 API 密钥和 API 密钥密文。输入后，程序会加载实时库存目录（可按国家搜索筛选），每个商品显示国家、账户注册时长、单价、剩余库存以及最小/最大购买数量。设置数量后点击“购买”。\n\n" +
            "之后一切自动完成：程序下单、将收据保存到 Data\\DatamollReceipts、下载交付的账户压缩包、安全解压，并将内容分类放入对应文件夹——.session+.json 文件对放入 Data\\Accounts，tdata 文件夹放入 Data\\Tdata（同名的已有文件不会被覆盖）。随后程序会自动重新扫描账户存储，新账户会立即出现在“账户”页面——无需手动搬移任何文件。购买结果摘要会显示交付数量、以 session/tdata 方式导入的数量、跳过的数量，以及程序中新注册的账户总数。");

        // ------------------------------------------------------------------
        // 9. Sending
        // ------------------------------------------------------------------
        table.Add("Manual.Sending.Title", "Рассылки (по ID и по номерам)", "Sending (by ID & by Numbers)", "群发（按 ID 和按号码）");
        table.Add("Manual.Sending.Body",
            "Две похожие задачи: «Sending SMS by ID» отправляет сообщения по числовым Telegram ID из загруженной базы, «Send by numbers» — по номерам телефона. Обе принимают текст сообщения (с поддержкой шаблонов и спинтакса), медиафайлы, ссылки для форварда или пост из Postbot, и распределяют получателей между выбранными отправителями.\n\n" +
            "Настраиваются: диапазон паузы между отправками, число одновременных потоков, максимальное время ожидания при флуд-лимите, автостоп по числу банов/спамблоков/флудвейтов, требование прокси (включено по умолчанию — см. раздел «Защита от банов»), а также дополнительные действия вроде удаления диалога после отправки, закрепления сообщения, автоматического ответа боту-репостеру и т.д.\n\n" +
            "Если на бэкенде включён прогрев новых аккаунтов, недавно добавленные отправители автоматически получают более медленный темп и меньший дневной лимит — вручную ничего указывать не нужно, это происходит прозрачно.\n\n" +
            "Рассылку можно запускать разово или добавить в «Плановые кампании», чтобы она повторялась по расписанию.",
            "Two similar jobs: \"Sending SMS by ID\" sends messages to numeric Telegram IDs from an uploaded database, \"Send by numbers\" sends by phone number instead. Both accept message text (with template and spintax support), media files, forward links or a Postbot post, and split recipients across the selected senders.\n\n" +
            "Configurable: the delay range between sends, number of concurrent streams, max FloodWait tolerance, auto-stop by ban/spam-block/flood-wait count, require-proxy (on by default — see \"Ban Protection\"), plus extras like deleting the dialog after sending, pinning the message, auto-replying to a repost bot, and more.\n\n" +
            "If new-account warmup is enabled on the backend, recently added senders automatically get a slower pace and a lower daily cap — nothing to configure by hand, it happens transparently.\n\n" +
            "A send job can run once, or be added to \"Scheduled Campaigns\" to repeat on a schedule.",
            "两个类似的任务：“Sending SMS by ID”按上传的数据库中的数字 Telegram ID 发送消息，“Send by numbers”则按手机号发送。两者都支持消息文本（支持模板和 spintax 花式文本）、媒体文件、转发链接或 Postbot 帖子，并将收件人分配给所选的发送账户。\n\n" +
            "可配置项包括：发送间隔范围、并发流数量、最大洪水限制等待时间、按封号/限流/洪水限制次数自动停止、要求使用代理（默认开启——见“防封号保护”一节），以及发送后删除对话、置顶消息、自动回复转发机器人等附加操作。\n\n" +
            "如果后端启用了新账户预热，最近添加的发送账户会自动以更慢的节奏和更低的每日上限运行——无需手动设置，系统会自动处理。\n\n" +
            "群发任务既可以单次运行，也可以添加到“计划任务”中按计划重复执行。");

        // ------------------------------------------------------------------
        // 10. Engagement & Stories
        // ------------------------------------------------------------------
        table.Add("Manual.Engagement.Title", "Накрутка и Сторис", "Engagement & Stories", "互动增长与快拍");
        table.Add("Manual.Engagement.Body",
            "«Накрутка» выполняет одно из четырёх действий на конкретном посте: реакция, просмотр, голос в опросе или комментарий — каждый выбранный аккаунт делает это ровно один раз (повторный запуск тем же аккаунтом просто перезаписывает предыдущее действие, как и работает сам Telegram).\n\n" +
            "«Сторис» — просмотр и реакция на чужую сторис, либо публикация своей сторис (фото/видео) от аккаунтов пула.\n\n" +
            "Обе задачи используют одинаковую систему «умных лимитов»: количество параллельных потоков, случайная пауза перед стартом каждого аккаунта (чтобы не все ударили по Telegram в одну секунду), и дневной лимит на аккаунт по типу действия — у просмотров сторис лимит особенно низкий (1–2 в день), потому что это ограничение самого Telegram, а не программы. Прогрев новых аккаунтов (если включён) дополнительно ужесточает этот лимит для недавно добавленных аккаунтов.\n\n" +
            "Как и рассылки, обе задачи по умолчанию требуют прокси у выбранных аккаунтов и не дадут запустить группу аккаунтов на одном общем прокси.",
            "\"Engagement\" performs one of four actions on a specific post: reaction, view, poll vote, or comment — each selected account does it exactly once (running it again with the same account just overwrites the previous action, matching how Telegram itself behaves).\n\n" +
            "\"Stories\" covers viewing/reacting to someone else's story, or posting your own story (photo/video) from pool accounts.\n\n" +
            "Both jobs share the same \"smart limits\" system: a configurable number of parallel streams, a randomized delay before each account starts (so they don't all hit Telegram in the same instant), and a per-account daily cap by action type — story views in particular are capped very low (1-2/day) because that's Telegram's own limit, not the app's. New-account warmup, if enabled, tightens that cap further for recently added accounts.\n\n" +
            "Like sending jobs, both require a proxy on selected accounts by default and won't start a group of accounts sharing one proxy.",
            "“互动增长”功能会在指定帖子上执行以下四种操作之一：点赞（反应）、浏览、投票或评论——每个所选账户只执行一次（同一账户再次运行只会覆盖之前的操作，这与 Telegram 自身的行为一致）。\n\n" +
            "“快拍”功能包括浏览/回应他人的快拍，或用账户池中的账户发布自己的快拍（图片/视频）。\n\n" +
            "两项任务共用同一套“智能限制”系统：可配置的并行流数量、每个账户启动前的随机延迟（避免同一时刻集中冲击 Telegram）、以及按操作类型的每账户每日上限——快拍浏览的上限尤其低（每天 1-2 次），因为这是 Telegram 自身的限制，而非程序设定。如果启用了新账户预热，该上限对于最近添加的账户会进一步收紧。\n\n" +
            "与群发任务一样，这两项功能默认要求所选账户使用代理，并且不允许一组共用同一代理的账户同时运行。");

        // ------------------------------------------------------------------
        // 11. Automation
        // ------------------------------------------------------------------
        table.Add("Manual.Automation.Title", "Плановые кампании, инвайт и проверка номеров", "Scheduling, Invites & Number Checking", "计划任务、邀请与号码检测");
        table.Add("Manual.Automation.Body",
            "«Плановые кампании» позволяют взять уже настроенную рассылку (по ID или по номерам) и запускать её не вручную, а по расписанию — один раз в заданное время или с повтором через заданный интервал часов, с ограничением по числу повторов или без него.\n\n" +
            "«Invite by number» рассылает приглашения (ссылку на канал/группу) по списку получателей от набора пар «отправитель — своя пригласительная ссылка» — удобно, когда у разных отправителей разные ссылки на разные объекты приглашения.\n\n" +
            "«Number checker» проверяет список телефонных номеров на наличие зарегистрированного Telegram-аккаунта, используя живые аккаунты пула в качестве проверяющих (забаненные, неавторизованные, в спамблоке или заморозке — исключаются автоматически). Можно запросить дополнительно данные профиля и определение пола. Результаты сохраняются в Data\\Exports\\number_checker.xlsx и их можно переиспользовать в следующей проверке через «использовать существующие результаты».",
            "\"Scheduled Campaigns\" lets you take an already-configured send job (by ID or by numbers) and run it on a schedule instead of by hand — once at a set time, or repeating on a set hourly interval, with or without a cap on how many times it repeats.\n\n" +
            "\"Invite by number\" sends invites (a channel/group link) to a list of recipients from a set of \"sender — that sender's own invite link\" pairs — useful when different senders hand out links to different destinations.\n\n" +
            "\"Number Checker\" checks a list of phone numbers for a registered Telegram account, using live pool accounts as the checking senders (banned/unauthorized/spam-blocked/frozen accounts are excluded automatically). You can optionally request profile data and gender detection. Results are saved to Data\\Exports\\number_checker.xlsx and can be reused for a follow-up check via \"use existing results\".",
            "“计划任务”功能可以将已经配置好的群发任务（按 ID 或按号码）设置为按计划自动运行，而不是手动启动——可以设置在指定时间运行一次，或按指定小时间隔重复运行，并可设置或不设置重复次数上限。\n\n" +
            "“Invite by number”功能会根据一组“发送账户—该账户专属邀请链接”的配对，向收件人列表发送邀请（频道/群组链接）——适合不同发送账户需要分发不同邀请目标链接的场景。\n\n" +
            "“Number checker”功能使用账户池中在线的账户作为检测账户（已封号/未授权/被限流/冻结的账户会自动排除），检测一批手机号是否已注册 Telegram 账户，还可以选择同时获取资料信息和性别识别。结果保存在 Data\\Exports\\number_checker.xlsx 中，可通过“使用已有结果”在后续检测中复用。");

        // ------------------------------------------------------------------
        // 12. Parsing & tools
        // ------------------------------------------------------------------
        table.Add("Manual.Parsing.Title", "Парсинг и вспомогательные инструменты", "Parsing & Utility Tools", "数据抓取与辅助工具");
        table.Add("Manual.Parsing.Body",
            "«Парсинг» собирает данные из чатов/каналов Telegram: выбираете источники поиском по уже известным чатам, стратегию (авто, участники, комментарии, сообщения, реакции, опросы, служебные сообщения, топик по ID) и фильтры — активность за последние N дней, пол, наличие аватара, премиум-статус, исключение ботов. Результат можно выгрузить целиком, сводкой или по источникам; по завершении показывается ссылка на файл базы и на скачивание txt, плюс статистика (с username, с телефоном, премиум, боты).\n\n" +
            "«Tdata» и «Session→Tdata» — конвертеры в обе стороны между .session-файлами и папками Telegram Desktop; подробности форматов — в разделе «Аккаунты».\n\n" +
            "«JSON-генератор» проставляет отпечатки устройств пачке сессий без .json — подробности в разделе «Отпечатки устройств».\n\n" +
            "«Text Randomizer» — инструмент подмены символов на визуально похожие (кириллица ⇄ похожая латиница), чтобы одинаковый по смыслу текст не выглядел байт-в-байт одинаковым при массовой отправке. Работает полностью локально, без бэкенда: вставляете шаблон замены (или включаете готовый набор), вставляете основной текст, жмёте «Создать рандомизацию» — получаете текст-спинтакс с вариантами `{a|б}`; «Сгенерировать один» разворачивает такой спинтакс в один конкретный вариант.",
            "\"Parsing\" collects data from Telegram chats/channels: pick sources by searching already-known chats, choose a strategy (auto, members, comments, messages, reactions, polls, system messages, a topic by ID), and set filters — active within the last N days, gender, has-avatar, premium status, exclude bots. Export as full, summary, or by-source; when finished you get a link to the database file and a downloadable txt, plus stats (with username, with phone, premium, bots).\n\n" +
            "\"Tdata\" and \"Session→Tdata\" convert both directions between .session files and Telegram Desktop folders; format details are in \"Accounts\".\n\n" +
            "\"JSON Generator\" stamps device fingerprints onto a batch of sessions with no .json — details in \"Device Fingerprints\".\n\n" +
            "\"Text Randomizer\" swaps characters for visually similar look-alikes (Cyrillic ⇄ similar Latin) so an otherwise-identical message doesn't look byte-for-byte the same across a bulk send. Fully local, no backend involved: paste a replacement template (or toggle a built-in preset), paste the source text, click \"Create Randomization\" to get spintax with `{a|b}`-style options, then \"Generate One\" to resolve that spintax into one concrete variant.",
            "“数据抓取”功能从 Telegram 聊天/频道中收集数据：通过搜索已知聊天选择数据来源，选择策略（自动、成员、评论、消息、反应、投票、系统消息、按话题 ID），并设置过滤条件——最近 N 天内活跃、性别、是否有头像、会员状态、排除机器人。导出方式可选完整、摘要或按来源；完成后会提供数据库文件链接和可下载的 txt 文件，以及统计信息（有用户名、有手机号、会员、机器人数量）。\n\n" +
            "“Tdata”和“Session→Tdata”是 .session 文件与 Telegram Desktop 文件夹之间的双向转换工具；格式细节见“账户”一节。\n\n" +
            "“JSON 生成器”为一批没有 .json 文件的会话打上设备指纹——详情见“设备指纹”一节。\n\n" +
            "“Text Randomizer（文本随机化）”用视觉相似的字符替换文本（西里尔字母 ⇄ 相似的拉丁字母），使批量发送时内容相同的消息不会逐字节完全一致。该工具完全在本地运行，不涉及后端：粘贴替换模板（或启用内置预设），粘贴原始文本，点击“创建随机化”即可得到 `{a|b}` 形式的花式文本；“生成一个”则会将该花式文本解析为一个具体的变体。");

        // ------------------------------------------------------------------
        // 13. License & FAQ
        // ------------------------------------------------------------------
        table.Add("Manual.LicenseFaq.Title", "Лицензия и частые вопросы", "License & FAQ", "许可证与常见问题");
        table.Add("Manual.LicenseFaq.Body",
            "Лицензия активируется один раз при первой установке (окно TgPoolActivator.exe) и дальше программа сама периодически подтверждает её действие в фоне — вмешиваться не нужно. Если подписка истекла или ключ отозван, доступ к функциям блокируется до повторной активации новым ключом.\n\n" +
            "Q: Я скопировал файлы аккаунтов в папку, но их не видно.\n" +
            "A: Подождите до ~20 секунд (фоновая проверка) или откройте/обновите вкладку «Аккаунты» — это запускает проверку немедленно. Если аккаунт всё ещё не появился, скорее всего файл не подошёл ни под один формат — проверьте баннер на Дашборде: там будет указана причина по каждому непринятому файлу.\n\n" +
            "Q: Голый .session не подхватывается.\n" +
            "A: Для голых сессий без .json нужно один раз задать api_id и api_hash по умолчанию на вкладке «Аккаунты» (раскрывающийся блок сверху списка) — без этого такие файлы всегда пропускаются.\n\n" +
            "Q: Программа отказывается запускать задачу и пишет про прокси.\n" +
            "A: Это защита по умолчанию — у одного или нескольких выбранных аккаунтов нет прокси, либо несколько аккаунтов используют один и тот же прокси. Назначьте прокси на вкладке «Прокси» или отключите переключатель «Запретить отправку с непрокси-аккаунтов» в настройках конкретной задачи, если точно понимаете риск.\n\n" +
            "Q: Опасаюсь волны банов — что в первую очередь проверить?\n" +
            "A: Убедитесь, что у каждого аккаунта свой прокси (не общий), что у новых аккаунтов есть время «отлежаться» перед активным использованием, и что заданы разумные автостопы по банам/спамблокам на каждой задаче — подробнее в разделе «Защита от банов».\n\n" +
            "Q: Куда смотреть, если что-то не работает и нужна поддержка?\n" +
            "A: Данные для диагностики — в Data\\Logs (технические логи бэкенда) и Data\\Crashes (отчёты о падении самой программы).",
            "The license is activated once at first install (the TgPoolActivator.exe window), after which the app keeps confirming it in the background on its own — nothing to do manually. If the subscription expires or the key is revoked, feature access is blocked until reactivated with a new key.\n\n" +
            "Q: I copied account files into the folder, but they're not showing up.\n" +
            "A: Wait up to ~20 seconds (the background sweep) or open/refresh the Accounts tab, which triggers a check immediately. If the account still doesn't appear, the file most likely didn't match any supported format — check the Dashboard banner, it names the reason for every rejected file.\n\n" +
            "Q: A bare .session isn't being picked up.\n" +
            "A: For bare sessions with no .json, set a default api_id/api_hash once on the Accounts tab (the expander above the list) — without it, such files are always skipped.\n\n" +
            "Q: The app refuses to start a job and complains about a proxy.\n" +
            "A: That's the default safety net — one or more selected accounts has no proxy, or several selected accounts share the same one. Assign proxies on the Proxy tab, or turn off \"Require proxy\" in that job's settings if you fully understand the risk.\n\n" +
            "Q: I'm worried about a ban wave — what should I check first?\n" +
            "A: Make sure every account has its own proxy (not a shared one), that new accounts get time to \"age\" before heavy use, and that sensible auto-stop thresholds are set on every job — see \"Ban Protection\" for details.\n\n" +
            "Q: Where do I look if something's broken and I need support?\n" +
            "A: Diagnostic data lives in Data\\Logs (backend technical logs) and Data\\Crashes (crash reports for the app itself).",
            "许可证在首次安装时激活一次（TgPoolActivator.exe 窗口），此后程序会在后台自动定期确认其有效性——无需手动干预。如果订阅到期或密钥被吊销，功能会被锁定，直到用新密钥重新激活。\n\n" +
            "问：我把账户文件复制到文件夹里了，但没有显示出来。\n" +
            "答：请等待最多约 20 秒（后台扫描），或打开/刷新“账户”页面，这会立即触发检查。如果账户仍未出现，很可能是该文件不符合任何受支持的格式——请查看仪表盘的提示条，其中会列出每个被拒绝文件的具体原因。\n\n" +
            "问：裸 .session 文件没有被识别。\n" +
            "答：对于没有 .json 的裸会话文件，需要先在“账户”页面（列表上方的展开区）设置一次默认 api_id/api_hash——否则此类文件始终会被跳过。\n\n" +
            "问：程序拒绝启动任务，并提示与代理有关的问题。\n" +
            "答：这是默认的安全保护——一个或多个所选账户没有代理，或多个所选账户共用了同一个代理。请在“代理”页面为账户分配代理，或者在完全清楚风险的前提下，在该任务的设置中关闭“要求使用代理”开关。\n\n" +
            "问：担心出现批量封号——首先应该检查什么？\n" +
            "答：确保每个账户都有独立的代理（不与其他账户共用），新账户在投入大量使用前有足够的“养号”时间，并且在每个任务中都设置了合理的封号/限流自动停止阈值——详见“防封号保护”一节。\n\n" +
            "问：出现问题需要支持时应该查看哪里？\n" +
            "答：诊断数据位于 Data\\Logs（后端技术日志）和 Data\\Crashes（程序自身的崩溃报告）。");
    }
}
