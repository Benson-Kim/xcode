namespace Auth.Domain.Setup;

public sealed class PsvCompany : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private PsvCompany() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public string Name { get; private set; } = "";
     public string NormalizedName { get; private set; } = "";
     public DateOnly? ArchivedOn { get; private set; }

     public bool ActiveOn(DateOnly date) => ArchivedOn is null || ArchivedOn > date;

     public PsvCompany(Guid organizationId, string name)
     {
          if (organizationId == Guid.Empty)
               throw new ArgumentException("Organization is required.");
          OrganizationId = organizationId;
          Rename(name);
     }

     public bool Rename(string name)
     {
          var value = SetupValue.Name(name);
          if (value == Name) return false;
          Name = value;
          NormalizedName = value.ToUpperInvariant();
          return true;
     }

     public bool Archive(DateOnly date)
     {
          if (date == default) throw new ArgumentException("Archive date is required.");
          if (ArchivedOn is not null)
          {
               if (ArchivedOn != date) throw new ArgumentException("The company is already archived.");
               return false;
          }
          ArchivedOn = date;
          return true;
     }

     public bool Restore()
     {
          if (ArchivedOn is null) return false;
          ArchivedOn = null;
          return true;
     }
}

public static class SetupValue
{
     public static string Name(string? value, int maxLength = 160)
     {
          value = value?.Trim();
          if (string.IsNullOrWhiteSpace(value) || value.Length > maxLength)
               throw new ArgumentException($"Name must contain 1-{maxLength} characters.");

          return value;
     }
     public static decimal Money(decimal value)
     {
          if (value <= 0 || value > 999999999999.99m || decimal.Round(value, 2) != value)
               throw new ArgumentException("Amount must be positive with at most two decimal places.");

          return value;
     }

}