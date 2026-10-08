using Auth.Domain.Setup;
using Auth.Infrastructure;

namespace Auth.Application.Settings;

// The one way a change-log entry is written: each entry moves the organization's SettingsVersion exactly once and
// carries that version, which is what version-keyed caches rely on. before and after are stored as given, so every
// caller keeps its own JSON shape; audit events stay with the callers.
public sealed class SettingsChangeLog(AuthDb db, IOrganizationRepository organizations, IClock clock)
{
    public async Task<long> Record(Guid organizationId, Guid actorId, string correlationId, string section, Guid entityId,
        string before, string after, string reason, Guid? vehicleId = null, CancellationToken ct = default)
    {
        var organization = await organizations.Get(ct) ?? throw new UnauthorizedAccessException();
        organization.SettingsChanged();
        db.Set<OrganizationSettingsVersion>().Add(new(organizationId, actorId, organization.SettingsVersion, section, entityId,
            clock.UtcNow, before, after, reason, correlationId, vehicleId: vehicleId));
        return organization.SettingsVersion;
    }
}
