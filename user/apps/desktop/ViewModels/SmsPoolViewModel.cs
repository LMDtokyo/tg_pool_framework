using TgPoolLauncher.Services;

namespace TgPoolLauncher.ViewModels;

public sealed class SmsPoolViewModel : HeroSmsViewModel
{
    public SmsPoolViewModel(BackendClient backend)
        : base(backend, SmsActivationProviderConfig.SmsPool)
    {
    }
}
