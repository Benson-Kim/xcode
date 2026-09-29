namespace Auth.Application.Setup;

// For reads that any one of several permissions opens. Such a read runs through the pipeline with no single permission,
// which has already refused anyone who is not an active member of the organization.
public static class SetupPermissions
{
    public static async Task RequireAny(IOrganizationRepository organizations, SetupActor actor, IReadOnlyCollection<string> permissions, CancellationToken ct)
    {
        var granted = await organizations.Permissions(actor.UserId, ct);
        if (!permissions.Any(granted.Contains))
            throw new UnauthorizedAccessException();
    }
}
