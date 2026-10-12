namespace Auth.Domain.Setup;

// A span in which a scheduled item does not run: from the day it was paused through the day before it was resumed.
// Through is null while it is still paused. One resumed on the day it was paused covers no day at all.
public sealed class RecurringPause : IOrganizationEntity
{
    Guid IOrganizationEntity.OrganizationId
    {
        get => OrganizationId;
        set => throw new InvalidOperationException("Tenant cannot change.");
    }
    private RecurringPause() { }
    public Guid Id { get; private set; } = Guid.NewGuid();
    public Guid OrganizationId { get; private set; }
    public Guid ItemId { get; private set; }
    public DateOnly From { get; private set; }
    public DateOnly? Through { get; private set; }

    internal RecurringPause(Guid organizationId, Guid itemId, DateOnly from) =>
        (OrganizationId, ItemId, From) = (organizationId, itemId, from);

    public bool Open => Through is null;

    public bool Covers(DateOnly date) => date >= From && (Through is null || date <= Through);

    internal void End(DateOnly resumedOn) => Through = resumedOn.AddDays(-1);
}
