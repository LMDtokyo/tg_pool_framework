using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public sealed class GrizzlySmsViewModel : HeroSmsViewModel
{
    public GrizzlySmsViewModel(BackendClient backend)
        : base(backend, SmsActivationProviderConfig.GrizzlySms)
    {
    }
}
