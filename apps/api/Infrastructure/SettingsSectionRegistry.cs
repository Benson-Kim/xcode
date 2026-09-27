

using Auth.Domain;

namespace Auth.Infrastructure;

public interface ISettingsSection
{
     string Key { get; }
     Type DtoType { get; }
     object Defaults();
     void Validate(object value);
}

public sealed class SettingsSection<T>(string key, Action<T> validate) : ISettingsSection where T : new()
{
     public string Key => key;
     public Type DtoType => typeof(T);
     public object Defaults() => new T();
     public void Validate(object value) => validate((T)value);
}

public sealed class SettingsSectionRegistry
{
     public IReadOnlyDictionary<string, ISettingsSection> Sections { get; } = new ISettingsSection[]
     {
          new SettingsSection<OrganizationLocalization>("localization", x=> x.Validate()),
          new SettingsSection<OrganizationBranding>("branding", x=> x.Validate()),
          new SettingsSection<OrganizationSecurityPolicy>("securityPolicy", x=> x.Validate()),
     }.ToDictionary(x => x.Key);
}