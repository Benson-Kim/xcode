using Auth.Domain;
using Auth.Domain.Setup;
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

    // The expense categories and items of Web v2.8 (EXPENSE_CATS and EXPENSE_ITEMS).
    public static readonly (string Name, ExpenseBucket Bucket, string[] Items)[] ExpenseCatalog =
    [
        ("Garage and repairs", ExpenseBucket.RepairsAndMaintenance, ["Garage labour", "Spares", "Tyres", "Service and maintenance", "Body work", "Towing"]),
        ("Charges", ExpenseBucket.RecurringCharges, ["Parking", "City council", "SACCO fee", "Insurance", "Licence", "Inspection"]),
        ("Loans", ExpenseBucket.LoanRepayments, ["Loan repayment"]),
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

            var roles = await UserProvisioning.EnsureRoles(db, organization.Id, cancellationToken);

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
                if (membership is null) db.Memberships.Add(new OrganizationMembership { OrganizationId = organization.Id, UserId = user.Id, FirstName = email.Split('.')[0] is var first ? char.ToUpperInvariant(first[0]) + first[1..] : "Demo", LastName = email.Split('.')[1].Split('@')[0] is var last ? char.ToUpperInvariant(last[0]) + last[1..] : "User" });
                var role = roles.Single(x => x.Name == roleName);
                if (!await db.PersonRoles.IgnoreQueryFilters().AnyAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, cancellationToken)) db.PersonRoles.Add(new PersonRole { OrganizationId = organization.Id, UserId = user.Id, RoleId = role.Id });
                if (roleName is "Owner" or "Office admin" && !await db.SetupDataScopes.IgnoreQueryFilters().AnyAsync(x => x.OrganizationId == organization.Id && x.UserId == user.Id, cancellationToken)) db.SetupDataScopes.Add(new SetupDataScope { OrganizationId = organization.Id, UserId = user.Id, AllCompanies = true });
            }
            // Only into an empty catalog, so categories renamed, stopped or added during development survive restarts.
            if (!await db.Set<ExpenseCategory>().IgnoreQueryFilters().AnyAsync(x => x.OrganizationId == organization.Id, cancellationToken))
                foreach (var (name, bucket, items) in ExpenseCatalog)
                {
                    var category = new ExpenseCategory(organization.Id, name, bucket);
                    db.Add(category);
                    foreach (var item in items) db.Add(new ExpenseItem(category, item));
                }
            await db.SaveChangesAsync(cancellationToken);
        }
        finally { db.Provisioning = false; }
    }
}
