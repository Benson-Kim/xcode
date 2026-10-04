using Auth.Application;
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed record ProvisionUserRequest(string Email, string PhoneNumber, string? Role = null, string? FirstName = null, string? LastName = null, string? OrganizationName = null);

// Operator-only bootstrap and backfill: gives a person everything sign-in requires (active user,
// membership and role). Never reachable from a request; Program exposes it as --provision-user.
public static class UserProvisioning
{
    public const string DefaultRole = "Owner";

    public static async Task<User> Provision(AuthDb db, ProvisionUserRequest request, CancellationToken ct = default)
    {
        if (!System.Net.Mail.MailAddress.TryCreate(request.Email, out _)) throw new ArgumentException("A valid email is required.");
        var phone = PhoneNumber.Normalize(request.PhoneNumber);
        if (phone == "") throw new ArgumentException("A valid mobile number such as 0712345678 is required.");
        if (request.Role is not null && !PermissionCatalog.RolePermissions.ContainsKey(request.Role))
            throw new ArgumentException($"Unknown role. Use one of: {string.Join(", ", PermissionCatalog.RolePermissions.Keys)}.");
        var email = request.Email.Trim().ToLowerInvariant();

        db.Provisioning = true;
        try
        {
            var organization = await EnsureOrganization(db, request.OrganizationName, ct);
            var roles = await EnsureRoles(db, organization.Id, ct);

            if (await db.Users.AnyAsync(u => u.PhoneNumber == phone && u.Email != email, ct))
                throw new ArgumentException("That mobile number already belongs to someone else.");
            var user = await db.Users.SingleOrDefaultAsync(u => u.Email == email, ct);
            var wasExisting = user is not null;
            var oldPhone = user?.PhoneNumber;
            var oldStatus = user?.Status;
            if (user is null)
            {
                user = new User { Email = email };
                db.Users.Add(user);
            }
            user.PhoneNumber = phone;
            user.Status = UserStatus.Active;

            var (first, last) = NameFrom(email);
            var membership = await db.Memberships.IgnoreQueryFilters().SingleOrDefaultAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, ct);
            var membershipWasInactive = membership is { Active: false };
            if (membership is null)
                db.Memberships.Add(new OrganizationMembership { OrganizationId = organization.Id, UserId = user.Id, FirstName = request.FirstName?.Trim() ?? first, LastName = request.LastName?.Trim() ?? last });
            else
            {
                if (!membership.Active) membership.Reactivate();
                if (request.FirstName is not null) membership.FirstName = request.FirstName.Trim();
                if (request.LastName is not null) membership.LastName = request.LastName.Trim();
            }

            // An existing role is only replaced when the operator names one explicitly.
            var roleLink = await db.PersonRoles.IgnoreQueryFilters().SingleOrDefaultAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, ct);
            var previousRoleId = roleLink?.RoleId;
            var roleName = request.Role ?? (roleLink is null ? DefaultRole : roles.Single(x => x.Id == roleLink.RoleId).Name);
            var role = roles.Single(x => x.Name.Equals(roleName, StringComparison.OrdinalIgnoreCase));
            if (roleLink is not null && roleLink.RoleId != role.Id) { db.PersonRoles.Remove(roleLink); roleLink = null; }
            if (roleLink is null) db.PersonRoles.Add(new PersonRole { OrganizationId = organization.Id, UserId = user.Id, RoleId = role.Id });

            // Operator backfills can change the account's identity, membership or role. Invalidate every
            // previously issued credential so those changes take effect on all devices.
            if (wasExisting &&
                (oldPhone != phone || oldStatus != UserStatus.Active || membershipWasInactive || previousRoleId != role.Id))
            {
                user.SecurityVersion++;
                foreach (var device in await db.TrustedDevices.IgnoreQueryFilters().Where(x => x.UserId == user.Id).ToListAsync(ct))
                    device.Revoked = true;
                foreach (var token in await db.RefreshTokens.IgnoreQueryFilters().Where(x => x.UserId == user.Id).ToListAsync(ct))
                    token.Revoked = true;
            }

            if (role.Name is "Owner" or "Office admin" && !await db.SetupDataScopes.IgnoreQueryFilters().AnyAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, ct))
                db.SetupDataScopes.Add(new SetupDataScope { OrganizationId = organization.Id, UserId = user.Id, AllCompanies = true });

            await db.SaveChangesAsync(ct);
            return user;
        }
        finally { db.Provisioning = false; }
    }

    public static async Task<Organization> EnsureOrganization(AuthDb db, string? name, CancellationToken ct)
    {
        var organizations = await db.Organizations.IgnoreQueryFilters().ToListAsync(ct);
        if (organizations.Count > 1) throw new InvalidOperationException("More than one organization exists; provisioning supports a single organization.");
        if (organizations.Count == 1) return organizations[0];

        var organization = new Organization { Name = string.IsNullOrWhiteSpace(name) ? "My fleet" : name.Trim(), Slug = "my-fleet" };
        db.Organizations.Add(organization);
        db.Localizations.Add(new OrganizationLocalization { OrganizationId = organization.Id });
        db.Brandings.Add(new OrganizationBranding { OrganizationId = organization.Id });
        db.SecurityPolicies.Add(new OrganizationSecurityPolicy { OrganizationId = organization.Id });
        return organization;
    }

    // Adds missing catalog roles. A role's permissions live only in PermissionCatalog, so no RolePermission rows are
    // written; rows left by older versions are ignored (the table is kept until it is dropped).
    public static async Task<List<Role>> EnsureRoles(AuthDb db, Guid organizationId, CancellationToken ct)
    {
        var roles = await db.Roles.IgnoreQueryFilters().Where(x => x.OrganizationId == organizationId).ToListAsync(ct);
        foreach (var roleName in PermissionCatalog.RolePermissions.Keys)
            if (roles.All(x => !x.Name.Equals(roleName, StringComparison.OrdinalIgnoreCase)))
            {
                var role = new Role { OrganizationId = organizationId, Name = roleName };
                db.Roles.Add(role); roles.Add(role);
            }
        return roles;
    }

    private static (string First, string Last) NameFrom(string email)
    {
        var parts = email.Split('@')[0].Split('.', StringSplitOptions.RemoveEmptyEntries);
        static string Title(string value) => char.ToUpperInvariant(value[0]) + value[1..];
        return (parts.Length > 0 ? Title(parts[0]) : "New", parts.Length > 1 ? Title(parts[1]) : "Member");
    }
}
