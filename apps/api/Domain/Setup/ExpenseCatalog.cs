namespace Auth.Domain.Setup;

// Money out is tracked in these three buckets only. Fuel and crew pay are not tracked anywhere: the crew settle
// both out of the day's takings, so the revenue recorded is already net of them.
public enum ExpenseBucket
{
     RepairsAndMaintenance = 1,
     RecurringCharges = 2,
     LoanRepayments = 3
}

public static class ExpenseBuckets
{
     // The bucket a version reports under, and the only rule for it: the one stored with the version, or recurring
     // charges when a row carries none, so no cost drops out of money out. Savings are not money out and have none.
     public static ExpenseBucket? Of(RecurringKind kind, ExpenseBucket? stored) =>
          kind != RecurringKind.Cost ? null : stored ?? ExpenseBucket.RecurringCharges;

     public static string Label(ExpenseBucket bucket) => bucket switch
     {
          ExpenseBucket.RepairsAndMaintenance => "Repairs and maintenance",
          ExpenseBucket.RecurringCharges => "Recurring charges",
          ExpenseBucket.LoanRepayments => "Loan repayments",
          _ => throw new ArgumentException("Choose repairs and maintenance, recurring charges or loan repayments.")
     };
}

// A setup list people pick from: each category counts as one bucket and holds the items chosen on expenses.
// Nothing is deleted. A stopped category or item stays on the records that already use it and can be restored.
public sealed class ExpenseCategory : IOrganizationEntity
{
     public const int NameLength = 100;
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private ExpenseCategory() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public string Name { get; private set; } = "";
     public string NormalizedName { get; private set; } = "";
     public ExpenseBucket Bucket { get; private set; }
     public DateOnly? StoppedOn { get; private set; }

     public ExpenseCategory(Guid organizationId, string name, ExpenseBucket bucket)
     {
          if (organizationId == Guid.Empty)
               throw new ArgumentException("Organization is required.");
          OrganizationId = organizationId;
          Change(name, bucket);
     }

     public bool ActiveOn(DateOnly date) => StoppedOn is null || StoppedOn > date;

     public bool Change(string name, ExpenseBucket bucket)
     {
          _ = ExpenseBuckets.Label(bucket);
          var value = SetupValue.Name(name, NameLength);
          if (value == Name && bucket == Bucket) return false;
          (Name, NormalizedName, Bucket) = (value, value.ToUpperInvariant(), bucket);
          return true;
     }

     public bool Stop(DateOnly today)
     {
          if (StoppedOn is not null)
          {
               if (StoppedOn != today) throw new ArgumentException("It is already turned off. Turn it on first to cancel that.");
               return false;
          }
          StoppedOn = today;
          return true;
     }

     public bool Restore()
     {
          if (StoppedOn is null) return false;
          StoppedOn = null;
          return true;
     }
}

public sealed class ExpenseItem : IOrganizationEntity
{
     Guid IOrganizationEntity.OrganizationId
     {
          get => OrganizationId;
          set => throw new InvalidOperationException("Tenant cannot change.");
     }
     private ExpenseItem() { }
     public Guid Id { get; private set; } = Guid.NewGuid();
     public Guid OrganizationId { get; private set; }
     public Guid CategoryId { get; private set; }
     public string Name { get; private set; } = "";
     public string NormalizedName { get; private set; } = "";
     public DateOnly? StoppedOn { get; private set; }

     public ExpenseItem(ExpenseCategory category, string name)
     {
          (OrganizationId, CategoryId) = (category.OrganizationId, category.Id);
          Rename(name);
     }

     public bool ActiveOn(DateOnly date) => StoppedOn is null || StoppedOn > date;

     public bool Rename(string name)
     {
          var value = SetupValue.Name(name, ExpenseCategory.NameLength);
          if (value == Name) return false;
          (Name, NormalizedName) = (value, value.ToUpperInvariant());
          return true;
     }

     public bool Stop(DateOnly today)
     {
          if (StoppedOn is not null)
          {
               if (StoppedOn != today) throw new ArgumentException("It is already turned off. Turn it on first to cancel that.");
               return false;
          }
          StoppedOn = today;
          return true;
     }

     public bool Restore()
     {
          if (StoppedOn is null) return false;
          StoppedOn = null;
          return true;
     }
}
