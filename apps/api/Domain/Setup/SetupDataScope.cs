namespace Auth.Domain.Setup;
// Explicit data scope is separate from permissions: possessing an action never grants all data.

public sealed class SetupDataScope : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid UserId { get; set; }
     public bool AllCompanies { get; set; }
}


public sealed class SetupCompanyScope : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid UserId { get; set; }
     public Guid CompanyId { get; set; }
}


public sealed class SetupVehicleScope : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid UserId { get; set; }
     public Guid VehicleId { get; set; }
}

public sealed class RecurrenceFrequencyLookup
{
     public RecurrenceFrequency Id { get; set; }
     public string Name { get; set; } = "";
}


public sealed class RecurringKindLookup
{
     public RecurringKind Id { get; set; }
     public string Name { get; set; } = "";
}


public sealed class CostCategoryLookup
{
     public CostCategory Id { get; set; }
     public string Name { get; set; } = "";
}


public sealed class ExpenseBucketLookup
{
     public ExpenseBucket Id { get; set; }
     public string Name { get; set; } = "";
}
