using System.Windows;
using System.Windows.Controls;
using TgPoolLauncher.Localization;
using TgPoolLauncher.ViewModels;

namespace TgPoolLauncher.Views;

/// <summary>
/// The formatting toolbar (bold/italic/code/link/placeholder) manipulates the message
/// TextBox's selection/caret directly -- that state lives in the control, not something
/// MVVM binding exposes, so it's handled here rather than in CampaignViewModel.
/// </summary>
public partial class CampaignView : UserControl
{
    public CampaignView(CampaignViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
    }

    private bool IsHtmlMode => DataContext is CampaignViewModel { ParseMode: "html" };

    private void BoldButton_Click(object sender, RoutedEventArgs e) =>
        WrapSelection(IsHtmlMode ? "<b>" : "*", IsHtmlMode ? "</b>" : "*", LocalizationService.Instance["Campaign.PlaceholderBold"]);

    private void ItalicButton_Click(object sender, RoutedEventArgs e) =>
        WrapSelection(IsHtmlMode ? "<i>" : "_", IsHtmlMode ? "</i>" : "_", LocalizationService.Instance["Campaign.PlaceholderItalic"]);

    private void CodeButton_Click(object sender, RoutedEventArgs e) =>
        WrapSelection(IsHtmlMode ? "<code>" : "`", IsHtmlMode ? "</code>" : "`", LocalizationService.Instance["Campaign.PlaceholderCode"]);

    private void LinkButton_Click(object sender, RoutedEventArgs e)
    {
        var linkText = LocalizationService.Instance["Campaign.PlaceholderLinkText"];
        if (IsHtmlMode)
            WrapSelection("<a href=\"https://\">", "</a>", linkText);
        else
            InsertAtCaret($"[{linkText}](https://)");
    }

    private void PlaceholderButton_Click(object sender, RoutedEventArgs e) => InsertAtCaret("{first_name}");

    private void ClearButton_Click(object sender, RoutedEventArgs e)
    {
        if (DataContext is CampaignViewModel vm)
            vm.MessageText = "";
    }

    private void WrapSelection(string prefix, string suffix, string placeholderText)
    {
        var box = MessageTextBox;
        var selectionLength = box.SelectionLength;
        var start = box.SelectionStart;
        var inner = selectionLength > 0 ? box.SelectedText : placeholderText;

        box.Text = box.Text[..start] + prefix + inner + suffix + box.Text[(start + selectionLength)..];
        box.Focus();
        box.SelectionStart = start + prefix.Length;
        box.SelectionLength = inner.Length;
    }

    private void InsertAtCaret(string text)
    {
        var box = MessageTextBox;
        var start = box.SelectionStart;
        box.Text = box.Text[..start] + text + box.Text[(start + box.SelectionLength)..];
        box.Focus();
        box.SelectionStart = start + text.Length;
    }
}
