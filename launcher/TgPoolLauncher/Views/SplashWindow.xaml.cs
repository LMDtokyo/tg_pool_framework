using System.Windows;
using System.Windows.Media.Animation;

namespace TgPoolLauncher.Views;

public partial class SplashWindow : Window
{
    public SplashWindow()
    {
        InitializeComponent();
    }

    /// <summary>
    /// Fades in, holds, fades out -- ~5s total -- then closes itself. App.xaml.cs runs this
    /// concurrently with backend startup and awaits both before showing MainWindow, so a slow
    /// backend doesn't add its startup time on top of the splash's fixed duration.
    /// </summary>
    public async Task RunAsync()
    {
        Show();
        await FadeAsync(0, 1, TimeSpan.FromMilliseconds(600));
        await Task.Delay(TimeSpan.FromMilliseconds(3800));
        await FadeAsync(1, 0, TimeSpan.FromMilliseconds(600));
        Close();
    }

    private Task FadeAsync(double from, double to, TimeSpan duration)
    {
        var tcs = new TaskCompletionSource();
        var animation = new DoubleAnimation(from, to, duration) { FillBehavior = FillBehavior.HoldEnd };
        animation.Completed += (_, _) => tcs.TrySetResult();
        BeginAnimation(OpacityProperty, animation);
        return tcs.Task;
    }
}
