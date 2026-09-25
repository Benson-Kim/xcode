using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Application;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

// Development only: the demo logins from design/XCODE_Web.html and design/XCODE_Mobile.html.
public static class DemoSeed
{
    public static readonly (string PhoneNumber, string Email, string? Pin)[] Logins =
    [
        ("+254733520614", "antony.maina@shamayah.co.ke", "4826"),     // Owner
        ("+254722410355", "peter.otieno@zurigenesis.co.ke", "1379"),  // Office admin
        ("+254700111222", "brian.mwangi@metrotrans.co.ke", null),     // Fleet manager: sets a PIN with an email code
        ("+254712345678", "wanjiru.kamau@zurigenesis.co.ke", "2580"), // Revenue clerk
    ];


    // Adds missing people only, so a PIN changed or reset during development survives restarts.
    public static async Task Run(AuthDb db, CancellationToken cancellationToken = default)
    {
        db.Provisioning = true;
        try
        {
            var organization = await db.Organizations.IgnoreQueryFilters().SingleOrDefaultAsync(cancellationToken);
            if (organization is null)
            {
                organization = new Organization { Slug = "demo-fleet", Name = "Demo Fleet" };
                db.Organizations.Add(organization);
                db.Localizations.Add(new OrganizationLocalization { OrganizationId = organization.Id });
                db.Brandings.Add(new OrganizationBranding { OrganizationId = organization.Id });
                db.SecurityPolicies.Add(new OrganizationSecurityPolicy { OrganizationId = organization.Id });
            }

            var roleNames = new[] { "Owner", "Office admin", "Fleet manager", "Revenue clerk" };
            var roles = await db.Roles.IgnoreQueryFilters().Where(x => x.OrganizationId == organization.Id).ToListAsync(cancellationToken);
            foreach (var roleName in roleNames)
            {
                if (roles.All(x => x.Name != roleName))
                {
                    var role = new Role { OrganizationId = organization.Id, Name = roleName };
                    db.Roles.Add(role); roles.Add(role);
                }
            }
            await db.SaveChangesAsync(cancellationToken);
            foreach (var role in roles)
            {
                var permissions = PermissionCatalog.RolePermissions.GetValueOrDefault(role.Name, PermissionCatalog.All.ToArray());
                var existingPermissions = await db.RolePermissions.IgnoreQueryFilters().Where(x => x.OrganizationId == organization.Id && x.RoleId == role.Id).Select(x => x.Permission).ToListAsync(cancellationToken);
                db.RolePermissions.AddRange(PermissionCatalog.WithDependencies(permissions).Where(x => !existingPermissions.Contains(x)).Select(x => role.Grant(x)));
            }

            var users = await db.Users.ToDictionaryAsync(x => x.Email, StringComparer.OrdinalIgnoreCase, cancellationToken);
            foreach (var (phoneNumber, email, pin) in Logins)
            {
                if (!users.TryGetValue(email, out var user))
                {
                    user = new User { PhoneNumber = phoneNumber, Email = email, PinHash = pin is null ? null : PinHasher.Hash(pin) };
                    db.Users.Add(user); users[email] = user;
                }
                user.Status = UserStatus.Active;
                var roleName = email.StartsWith("antony.", StringComparison.OrdinalIgnoreCase) ? "Owner" : email.StartsWith("peter.", StringComparison.OrdinalIgnoreCase) ? "Office admin" : email.StartsWith("brian.", StringComparison.OrdinalIgnoreCase) ? "Fleet manager" : "Revenue clerk";
                var membership = await db.Memberships.IgnoreQueryFilters().SingleOrDefaultAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, cancellationToken);
                if (membership is null) db.Memberships.Add(new OrganizationMembership { OrganizationId = organization.Id, UserId = user.Id, FirstName = email.Split('.')[0] is var first ? char.ToUpperInvariant(first[0]) + first[1..] : "Demo", LastName = email.Split('.')[1].Split('@')[0] });
                var role = roles.Single(x => x.Name == roleName);
                if (!await db.PersonRoles.IgnoreQueryFilters().AnyAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, cancellationToken)) db.PersonRoles.Add(new PersonRole { OrganizationId = organization.Id, UserId = user.Id, RoleId = role.Id });
                if (roleName is "Owner" or "Office admin" && !await db.SetupDataScopes.IgnoreQueryFilters().AnyAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, cancellationToken)) db.SetupDataScopes.Add(new SetupDataScope { OrganizationId = organization.Id, UserId = user.Id, AllCompanies = true });
            }
            await db.SaveChangesAsync(cancellationToken);
        }
        finally { db.Provisioning = false; }
    }
}
