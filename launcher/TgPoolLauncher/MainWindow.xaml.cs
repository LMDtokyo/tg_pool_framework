using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;
using TgPoolLauncher.Localization;
using TgPoolLauncher.Models;
using TgPoolLauncher.ViewModels;
using TgPoolLauncher.Views;

namespace TgPoolLauncher;

public partial class MainWindow : Window
{
    private readonly AutoRegisterNavigationViewModel _autoRegisterNavigation;
    private bool _syncingChildSelection;

    public MainWindow(
        DashboardView dashboardView,
        AccountsView accountsView,
        CampaignView campaignView,
        ProxyCheckView proxyCheckView,
        ProxyPoolCheckerView proxyPoolCheckerView,
        TdataConvertView tdataConvertView,
        ParsingView parsingView,
        SessionConvertView sessionConvertView,
        JsonGeneratorView jsonGeneratorView,
        TextRandomizerView textRandomizerView,
        AutoRegisterHostView autoRegisterHostView,
        AutoRegisterNavigationViewModel autoRegisterNavigation)
    {
        InitializeComponent();
        _autoRegisterNavigation = autoRegisterNavigation;
        AutoRegisterMenu.DataContext = autoRegisterNavigation;
        InviteMenu.DataContext = autoRegisterNavigation;
        PhoneNumbersMenu.DataContext = autoRegisterNavigation;
        AutoRegisterMenu.SelectedItem = autoRegisterNavigation.SelectedPage;
        DashboardTab.Content = dashboardView;
        AccountsTab.Content = accountsView;
        CampaignTab.Content = campaignView;
        ProxyCheckTab.Content = proxyCheckView;
        ProxyPoolCheckerTab.Content = proxyPoolCheckerView;
        TdataConvertTab.Content = tdataConvertView;
        ParsingTab.Content = parsingView;
        SessionConvertTab.Content = sessionConvertView;
        JsonGeneratorTab.Content = jsonGeneratorView;
        TextRandomizerTab.Content = textRandomizerView;
        AutoRegisterTab.Content = autoRegisterHostView;
    }

    /// <summary>Called once by App.xaml.cs right after Show(), since the window starts at Opacity=0.</summary>
    public void FadeIn()
    {
        BeginAnimation(OpacityProperty, new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(450)));
    }

    private void MinimizeButton_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void MaximizeButton_Click(object sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private void CloseButton_Click(object sender, RoutedEventArgs e) => Close();

    private void AutoRegisterMenu_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_syncingChildSelection || AutoRegisterMenu.SelectedItem is not AutoRegisterPage page)
            return;

        ActivateAutoRegisterPage(page);
    }

    private void AutoRegisterMenu_PreviewMouseLeftButtonUp(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        if (FindAncestor<ListBoxItem>(e.OriginalSource as DependencyObject) is null)
            return;

        if (FindAncestor<ListBoxItem>(e.OriginalSource as DependencyObject)?.DataContext is AutoRegisterPage page)
            ActivateAutoRegisterPage(page);
    }

    private void PhoneNumbersMenu_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_syncingChildSelection || PhoneNumbersMenu.SelectedItem is not AutoRegisterPage page)
            return;

        ActivatePhoneNumberPage(page);
    }

    private void InviteMenu_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_syncingChildSelection || InviteMenu.SelectedItem is not AutoRegisterPage page)
            return;

        ActivateInvitePage(page);
    }

    private void PhoneNumbersMenu_PreviewMouseLeftButtonUp(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        if (FindAncestor<ListBoxItem>(e.OriginalSource as DependencyObject) is null)
            return;

        if (FindAncestor<ListBoxItem>(e.OriginalSource as DependencyObject)?.DataContext is AutoRegisterPage page)
            ActivatePhoneNumberPage(page);
    }

    private void InviteMenu_PreviewMouseLeftButtonUp(object sender, System.Windows.Input.MouseButtonEventArgs e)
    {
        if (FindAncestor<ListBoxItem>(e.OriginalSource as DependencyObject) is null)
            return;

        if (FindAncestor<ListBoxItem>(e.OriginalSource as DependencyObject)?.DataContext is AutoRegisterPage page)
            ActivateInvitePage(page);
    }

    private void RootTabs_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!ReferenceEquals(e.OriginalSource, RootTabs))
            return;
        if (RootTabs.SelectedItem == AutoRegisterTab)
            return;

        AutoRegisterMenu.SelectedItem = null;
        InviteMenu.SelectedItem = null;
        PhoneNumbersMenu.SelectedItem = null;
    }

    private void ActivateAutoRegisterPage(AutoRegisterPage page)
    {
        _autoRegisterNavigation.SelectedPage = page;
        SyncChildSelection(AutoRegisterMenu, page, InviteMenu, PhoneNumbersMenu);
        SelectAutoRegisterGroup();
    }

    private void ActivateInvitePage(AutoRegisterPage page)
    {
        _autoRegisterNavigation.SelectedPage = page;
        SyncChildSelection(InviteMenu, page, AutoRegisterMenu, PhoneNumbersMenu);
        SelectInviteGroup();
    }

    private void ActivatePhoneNumberPage(AutoRegisterPage page)
    {
        _autoRegisterNavigation.SelectedPage = page;
        SyncChildSelection(PhoneNumbersMenu, page, AutoRegisterMenu, InviteMenu);
        SelectPhoneNumbersGroup();
    }

    private void SyncChildSelection(ListBox activeMenu, AutoRegisterPage page, params ListBox[] inactiveMenus)
    {
        _syncingChildSelection = true;
        try
        {
            foreach (var inactiveMenu in inactiveMenus)
                inactiveMenu.SelectedItem = null;
            activeMenu.SelectedItem = page;
        }
        finally
        {
            _syncingChildSelection = false;
        }
    }

    private void SelectAutoRegisterGroup()
    {
        AutoRegisterTab.IsSelected = true;
        AutoRegisterExpander.IsExpanded = true;
    }

    private void SelectInviteGroup()
    {
        AutoRegisterTab.IsSelected = true;
        InviteExpander.IsExpanded = true;
    }

    private void SelectPhoneNumbersGroup()
    {
        AutoRegisterTab.IsSelected = true;
        PhoneNumbersExpander.IsExpanded = true;
    }

    private static T? FindAncestor<T>(DependencyObject? current)
        where T : DependencyObject
    {
        while (current is not null)
        {
            if (current is T match)
                return match;
            current = VisualTreeHelper.GetParent(current);
        }
        return null;
    }

    private void LanguageButton_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: string code } && Enum.TryParse<AppLanguage>(code, out var language))
            LocalizationService.Instance.CurrentLanguage = language;
    }
}
