namespace TgPoolLauncher.Localization.Strings;

internal static class TextRandomizerStrings
{
    public static void Register(Dictionary<AppLanguage, Dictionary<string, string>> table)
    {
        table.Add("TextRandomizer.MaskHeader", "МАСКА", "MASK", "字符掩码");
        table.Add("TextRandomizer.TemplateLabel", "Шаблон", "Template", "模板");
        table.Add("TextRandomizer.DirectionToggleLabel", "RU -> EN || EN -> RU", "RU -> EN || EN -> RU", "RU -> EN || EN -> RU");
        table.Add("TextRandomizer.CheckButton", "Проверить", "Check", "检查");
        table.Add("TextRandomizer.MainTextHeader", "ОСНОВНОЙ ТЕКСТ", "MAIN TEXT", "正文");
        table.Add("TextRandomizer.CreateRandomizationButton", "Создать рандомизацию", "Create Randomization", "创建随机化");
        table.Add("TextRandomizer.ResultHeader", "РЕЗУЛЬТАТ", "RESULT", "结果");
        table.Add("TextRandomizer.GenerateOneButton", "Сгенерировать один вариант", "Generate One", "生成一个版本");
        table.Add("TextRandomizer.TemplateReadyStatus", "Шаблон готов.", "Template is ready.", "模板已就绪。");
        table.Add("TextRandomizer.NoValidMasksStatus",
            "Валидные маски не найдены. Используйте синтаксис спина, например {O|0}.",
            "No valid masks found. Use spin syntax like {O|0}.",
            "未找到有效掩码。请使用类似 {O|0} 的替换语法。");
        table.Add("TextRandomizer.MasksReadyStatusFormat",
            "Готово масок: {0}.", "{0} masks are ready.", "已就绪 {0} 个掩码。");
        table.Add("TextRandomizer.NoMasksAppliedStatus",
            "Маски не были применены.", "No masks were applied.", "未应用任何掩码。");
        table.Add("TextRandomizer.RandomizationCreatedStatus",
            "Рандомизация создана.", "Randomization created.", "随机化已创建。");
        table.Add("TextRandomizer.OneVersionCreatedStatus",
            "Создан один рандомизированный вариант.", "One randomized version created.", "已生成一个随机化版本。");
    }
}
