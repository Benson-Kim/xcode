using System.Text.Json;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Application.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application;

public sealed class AccessUseCases(ISetupExecution execution, AuthDb db, IOrganizationRepository organizations, IClock clock)
{
    // Labels only, so every member can read them (for "Your access").
    public Task<IReadOnlyList<PermissionGroup>> Catalog(CancellationToken ct) => execution.Read("", _ => Task.FromResult(PermissionCatalog.Groups), ct);

    public Task<IReadOnlyList<AccessRole>> Roles(CancellationToken ct) => execution.Read("people.view", async actor =>
    {
        var roles = await UserProvisioning.EnsureRoles(db, actor.OrganizationId, ct);
        return (IReadOnlyList<AccessRole>)roles
            .OrderBy(x => x.Name)
            .Select(x => new AccessRole(x.Id, x.Name, PermissionCatalog.DefaultsFor(x.Name)))
            .ToList();
    }, ct);

    // Mirrors ValidateScope: only the companies and vehicles the editor may hand on.
    public Task<ScopeOptions> ScopeOptions(CancellationToken ct) => execution.Read("people.manage", async actor =>
    {
        var companies = await db.Set<PsvCompany>()
            .AsNoTracking()
            .Where(c => actor.AllCompanies || actor.CompanyIds.Contains(c.Id))
            .OrderBy(c => c.Name)
            .Select(c => new ScopeCompanyOption(c.Id, c.Name))
            .ToListAsync(ct);
        var vehicles = await db.Set<FleetVehicle>()
            .AsNoTracking()
            .Where(v => actor.AllCompanies || actor.VehicleIds.Contains(v.Id))
            .OrderBy(v => v.Registration)
            .Select(v => new ScopeVehicleOption(v.Id, v.Registration, v.CompanyId))
            .ToListAsync(ct);
        return new ScopeOptions(companies, vehicles);
    }, ct);

    public Task<Page<PersonDto>> List(int page, int pageSize, CancellationToken ct) => execution.Read("people.view", async actor =>
    {
        SetupPagination.Validate(page, pageSize);
        var people = await LoadPeople(actor, ct);
        var rows = people
            .OrderBy(x => x.Membership.LastName)
            .ThenBy(x => x.Membership.FirstName)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(ToDto)
            .ToArray();
        return new Page<PersonDto>(rows, page, pageSize, people.Count);
    }, ct);

    public Task<PersonDto> Get(Guid id, CancellationToken ct) => execution.Read("people.view", async actor =>
        ToDto((await LoadPeople(actor, ct)).SingleOrDefault(x => x.User.Id == id) ?? throw new KeyNotFoundException()), ct);

    public Task<Guid> Save(Guid? id, SavePerson input, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        Validate(input);
        var role = await EnsureRole(input.Role, actor.OrganizationId, ct);
        var people = await LoadPeople(actor, ct);
        var target = id is null ? null : people.SingleOrDefault(x => x.User.Id == id.Value);

        if (id is not null && target is null)
            throw new KeyNotFoundException();
        if (id == actor.UserId)
            throw new ArgumentException("You cannot change your own access here.");

        var actorIsOwner = await IsOwner(actor.UserId, ct);
        if (IsOwnerRole(role) && !actorIsOwner)
            throw new UnauthorizedAccessException();
        if (target is not null)
            await EnsureMayManage(actor, target, ct);

        ValidateScope(actor, input);

        var permissions = PermissionCatalog.WithDependencies(input.Permissions);
        if (permissions.Any(x => !PermissionCatalog.All.Contains(x, StringComparer.Ordinal)))
            throw new ArgumentException("Unknown permission.");

        await AuthorizeAccessChange(actor, target, role, permissions, input.ApprovalLimit, ct);
        var phone = PhoneNumber.Normalize(input.PhoneNumber);
        var email = input.Email.Trim().ToLowerInvariant();
        var before = target is null ? null : PersonSnapshot.Of(target);
        var after = new PersonSnapshot(input.FirstName.Trim(), input.LastName.Trim(), email, phone, role.Name, target?.Membership.Active ?? true,
            input.ScopeMode, input.ScopeMode == "companies" ? [.. input.CompanyIds.Distinct().Order()] : [],
            input.ScopeMode == "vehicles" ? [.. input.VehicleIds.Distinct().Order()] : [],
            [.. Effective(role, permissions).Order(StringComparer.Ordinal)], input.ApprovalLimit);
        var signInDetailsChanged = target is not null &&
            (!string.Equals(target.User.Email, email, StringComparison.OrdinalIgnoreCase) || target.User.PhoneNumber != phone);
        if (signInDetailsChanged)
            await AuthorizeSignInDetailsChange(actor, target!, actorIsOwner, ct);
        if (await db.Users.AnyAsync(x => (x.PhoneNumber == phone || x.Email == email) && x.Id != id, ct))
            throw new ArgumentException("That mobile number or email already belongs to someone.");

        if (target is null)
        {
            var user = new User { PhoneNumber = phone, Email = email };
            db.Users.Add(user);
            db.Memberships.Add(new OrganizationMembership
            {
                OrganizationId = actor.OrganizationId,
                UserId = user.Id,
                FirstName = input.FirstName.Trim(),
                LastName = input.LastName.Trim(),
                ApprovalLimit = input.ApprovalLimit
            });
            db.PersonRoles.Add(new PersonRole
            {
                OrganizationId = actor.OrganizationId,
                UserId = user.Id,
                RoleId = role.Id
            });
            ApplyScope(actor.OrganizationId, user.Id, input);
            ApplyOverrides(actor.OrganizationId, user.Id, role, permissions);
            Audit(actor, "person.created", user.Id, input.Role);
            await RecordHistory(actor, user.Id, null, after, $"Added {after.Name} as {role.Name}", ct);
            return user.Id;
        }

        if (signInDetailsChanged)
        {
            // Existing sessions and trusted devices belonged to the old details: end them, so the next sign-in
            // verifies this device with a code sent to the email now on file. The PIN itself is kept.
            Audit(actor, "person.sign_in_details_changed", target.User.Id,
                JsonSerializer.Serialize(new { email, phoneNumber = phone }),
                JsonSerializer.Serialize(new { email = target.User.Email, phoneNumber = target.User.PhoneNumber }));
            target.User.SecurityVersion++;
            await RevokeSessions(target.User.Id, ct);
        }
        target.Membership.FirstName = input.FirstName.Trim();
        target.Membership.LastName = input.LastName.Trim();
        target.Membership.ApprovalLimit = input.ApprovalLimit;
        target.User.Email = email;
        target.User.PhoneNumber = phone;
        db.PersonRoles
            .RemoveRange(db.PersonRoles.Where(x => x.UserId == target.User.Id));
        db.PermissionOverrides
            .RemoveRange(db.PermissionOverrides.Where(x => x.UserId == target.User.Id));
        db.SetupDataScopes
            .RemoveRange(db.SetupDataScopes.Where(x => x.UserId == target.User.Id));
        db.SetupCompanyScopes
            .RemoveRange(db.SetupCompanyScopes.Where(x => x.UserId == target.User.Id));
        db.SetupVehicleScopes
            .RemoveRange(db.SetupVehicleScopes.Where(x => x.UserId == target.User.Id));
        db.PersonRoles.Add(new PersonRole
        {
            OrganizationId = actor.OrganizationId,
            UserId = target.User.Id,
            RoleId = role.Id
        });
        ApplyScope(actor.OrganizationId, target.User.Id, input);
        ApplyOverrides(actor.OrganizationId, target.User.Id, role, permissions);
        Audit(actor, "person.updated", target.User.Id, input.Role);
        var changes = before!.Changes(after);
        // Their access token carries their name, role and permissions. Bumping the version makes it fail on the next
        // request, and the client renews it with the new values, so the person is not signed out. Data scope is
        // checked against the database on every request, so it needs no renewal.
        if (changes.Intersect(["name", "role", "single permissions"]).Any())
            target.User.SecurityVersion++;
        if (changes.Count > 0)
            await RecordHistory(actor, target.User.Id, before, after, $"Changed {JoinWords(changes)} for {after.Name}", ct);
        return target.User.Id;
    }, ct);

    public Task<Guid> SetActive(Guid id, bool active, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        if (id == actor.UserId)
            throw new ArgumentException("You cannot deactivate your own access.");
        var target = (await LoadPeople(actor, ct)).SingleOrDefault(x => x.User.Id == id) ?? throw new KeyNotFoundException();
        await EnsureMayManage(actor, target, ct);
        var before = PersonSnapshot.Of(target);
        if (before.Active != active)
            await RecordHistory(actor, id, before, before with { Active = active },
                active ? $"Restored access for {before.Name}" : $"Removed access for {before.Name}", ct);
        if (active)
        {
            target.Membership.Reactivate();
            target.User.Status = UserStatus.Active;
        }
        else
        {
            target.Membership.Deactivate();
            target.User.Status = UserStatus.Removed;
            target.User.SecurityVersion++;
            await RevokeSessions(id, ct);
        }
        Audit(actor, active ? "person.activated" : "person.deactivated", id, null);
        return id;
    }, ct);

    public Task<Guid> SignOut(Guid id, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        if (id == actor.UserId)
            throw new ArgumentException("Use sign out for your own session.");
        var target = (await LoadPeople(actor, ct)).SingleOrDefault(x => x.User.Id == id) ?? throw new KeyNotFoundException();
        await EnsureMayManage(actor, target, ct);
        await RevokeSessions(id, ct);
        Audit(actor, "person.sessions_revoked", id, null);
        var snapshot = PersonSnapshot.Of(target);
        await RecordHistory(actor, id, snapshot, snapshot, $"Signed {snapshot.Name} out of every device", ct);
        return id;
    }, ct);

    private async Task<List<AccessPerson>> LoadPeople(SetupActor actor, CancellationToken ct)
    {
        var memberships = await db.Memberships.ToListAsync(ct);
        var users = await db.Users
            .Where(x => memberships.Select(m => m.UserId).Contains(x.Id))
            .ToDictionaryAsync(x => x.Id, ct);
        var personRoles = await db.PersonRoles.ToListAsync(ct);
        var roles = await db.Roles.ToDictionaryAsync(x => x.Id, ct);
        var overrides = await db.PermissionOverrides.ToListAsync(ct);
        var dataScopes = await db.SetupDataScopes.ToListAsync(ct);
        var companyScopes = await db.SetupCompanyScopes.ToListAsync(ct);
        var vehicleScopes = await db.SetupVehicleScopes.ToListAsync(ct);
        var result = new List<AccessPerson>();
        foreach (var membership in memberships)
        {
            if (!users.TryGetValue(membership.UserId, out var user)) continue;
            var roleLink = personRoles.SingleOrDefault(x => x.UserId == user.Id);
            if (roleLink is null || !roles.TryGetValue(roleLink.RoleId, out var role)) continue;
            var scope = dataScopes.SingleOrDefault(x => x.UserId == user.Id);
            var companyIds = companyScopes.Where(x => x.UserId == user.Id).Select(x => x.CompanyId).ToList();
            var vehicleIds = vehicleScopes.Where(x => x.UserId == user.Id).Select(x => x.VehicleId).ToList();
            var visible = user.Id == actor.UserId || actor.AllCompanies || scope?.AllCompanies == true && actor.AllCompanies || companyIds.Any(actor.CompanyIds.Contains) || vehicleIds.Any(actor.VehicleIds.Contains);
            if (!visible) continue;
            // Assigned permissions, regardless of whether the person is active: editing an inactive person must not
            // lose their configuration. Inactive members are refused at sign-in and on every request instead.
            var permissions = new EffectivePermissionResolver()
                .Resolve(PermissionCatalog.DefaultsFor(role.Name), overrides.Where(x => x.UserId == user.Id));
            result.Add(new AccessPerson(user, membership, role, permissions, scope, companyIds, vehicleIds));
        }
        return result;
    }

    private static string ScopeModeOf(AccessPerson x) => x.Scope?.AllCompanies == true ? "all" : x.CompanyIds.Count > 0 ? "companies" : "vehicles";

    private static PersonDto ToDto(AccessPerson x) => new(
        x.User.Id,
        x.Membership.FirstName,
        x.Membership.LastName,
        x.User.Email,
        x.User.PhoneNumber,
        x.Role.Name,
        x.Membership.Active,
        ScopeModeOf(x),
        x.CompanyIds,
        x.VehicleIds,
        x.Permissions.ToArray(),
        x.Membership.ApprovalLimit,
        x.User.PinHash is not null
    );

    private static void Validate(SavePerson input)
    {
        if (string.IsNullOrWhiteSpace(input.FirstName) || input.FirstName.Length > 100 || string.IsNullOrWhiteSpace(input.LastName) || input.LastName.Length > 100)
            throw new ArgumentException("First and last name are required.");
        if (!System.Net.Mail.MailAddress.TryCreate(input.Email, out _))
            throw new ArgumentException("A valid email is required.");
        if (PhoneNumber.Normalize(input.PhoneNumber) == "")
            throw new ArgumentException("A valid mobile number is required.");
        if (input.ScopeMode is not ("all" or "companies" or "vehicles"))
            throw new ArgumentException("Choose a data scope.");
        if (input.ScopeMode == "companies" && input.CompanyIds.Count == 0 || input.ScopeMode == "vehicles" && input.VehicleIds.Count == 0)
            throw new ArgumentException("Choose at least one item in the data scope.");
        if (input.Permissions.Count == 0 || input.ApprovalLimit is < 0)
            throw new ArgumentException("Permissions and approval limit are invalid.");
    }

    private static void ValidateScope(SetupActor actor, SavePerson input)
    {
        if (input.ScopeMode == "all" && !actor.AllCompanies)
            throw new UnauthorizedAccessException();
        if (input.ScopeMode == "companies" && input.CompanyIds.Any(x => !actor.AllCompanies && !actor.CompanyIds.Contains(x)))
            throw new UnauthorizedAccessException();
        if (input.ScopeMode == "vehicles" && input.VehicleIds.Any(x => !actor.AllCompanies && !actor.VehicleIds.Contains(x)))
            throw new UnauthorizedAccessException();
    }

    private void ApplyScope(Guid organizationId, Guid userId, SavePerson input)
    {
        if (input.ScopeMode == "all")
            db.SetupDataScopes.Add(new SetupDataScope
            {
                OrganizationId = organizationId,
                UserId = userId,
                AllCompanies = true
            });
        if (input.ScopeMode == "companies")
            db.SetupCompanyScopes.AddRange(
                input.CompanyIds.Select(x => new SetupCompanyScope
                {
                    OrganizationId = organizationId,
                    UserId = userId,
                    CompanyId = x
                })
            );
        if (input.ScopeMode == "vehicles")
            db.SetupVehicleScopes.AddRange(
                input.VehicleIds.Select(x => new SetupVehicleScope
                {
                    OrganizationId = organizationId,
                    UserId = userId,
                    VehicleId = x
                })
            );
    }

    private void ApplyOverrides(Guid organizationId, Guid userId, Role role, IReadOnlyList<string> permissions)
        => db.PermissionOverrides.AddRange(Overrides(organizationId, userId, role, permissions));

    private static IEnumerable<PersonPermissionOverride> Overrides(Guid organizationId, Guid userId, Role role, IReadOnlyList<string> permissions)
    {
        var defaults = PermissionCatalog.DefaultsFor(role.Name);
        return PermissionCatalog.All
            .Where(x => defaults.Contains(x) != permissions.Contains(x))
            .Select(x => new PersonPermissionOverride
            {
                OrganizationId = organizationId,
                UserId = userId,
                Permission = x,
                Granted = permissions.Contains(x)
            });
    }

    // What the person would hold with this role and these requested permissions, once overrides are applied.
    private static IReadOnlySet<string> Effective(Role role, IReadOnlyList<string> permissions) => new EffectivePermissionResolver()
        .Resolve(PermissionCatalog.DefaultsFor(role.Name), Overrides(Guid.Empty, Guid.Empty, role, permissions));

    // people.manage covers who someone is, their role and their data scope. Departing from the role's defaults
    // (single permissions, approval limit) needs access.manage, and nobody can grant a permission they lack.
    private async Task AuthorizeAccessChange(SetupActor actor, AccessPerson? target, Role role, IReadOnlyList<string> permissions, decimal? approvalLimit, CancellationToken ct)
    {
        var before = target is null ? Deviation.None : Deviation.From(PermissionCatalog.DefaultsFor(target.Role.Name), target.Permissions);
        var after = Deviation.From(PermissionCatalog.DefaultsFor(role.Name), Effective(role, permissions));
        if (after.Same(before) && approvalLimit == target?.Membership.ApprovalLimit)
            return;
        var held = await organizations.Permissions(actor.UserId, ct);
        if (!held.Contains("access.manage") || after.Granted.Except(before.Granted).Any(x => !held.Contains(x)))
            throw new UnauthorizedAccessException();
    }

    // Only an Owner may edit, deactivate or sign out an Owner.
    private async Task EnsureMayManage(SetupActor actor, AccessPerson target, CancellationToken ct)
    {
        if (IsOwnerRole(target.Role) && !await IsOwner(actor.UserId, ct))
            throw new UnauthorizedAccessException();
    }

    // Sign-in codes go to the person's email, so whoever sets their email and mobile can sign in as them. That is
    // only allowed for someone who could have granted them everything they hold anyway: an Owner, or an editor
    // whose own permissions and assignable roles cover all of the person's (and, for an approval limit, access.manage).
    private async Task AuthorizeSignInDetailsChange(SetupActor actor, AccessPerson target, bool actorIsOwner, CancellationToken ct)
    {
        if (actorIsOwner)
            return;
        var held = await organizations.Permissions(actor.UserId, ct);
        var grantable = PermissionCatalog.RolePermissions.Keys
            .Where(x => !x.Equals("Owner", StringComparison.OrdinalIgnoreCase))
            .SelectMany(PermissionCatalog.DefaultsFor)
            .Concat(held)
            .ToHashSet(StringComparer.Ordinal);
        if (target.Permissions.Any(x => !grantable.Contains(x)) || (target.Membership.ApprovalLimit is not null && !held.Contains("access.manage")))
            throw new UnauthorizedAccessException();
    }

    private static bool IsOwnerRole(Role role) => role.Name.Equals("Owner", StringComparison.OrdinalIgnoreCase);

    private async Task<Role> EnsureRole(string name, Guid organizationId, CancellationToken ct)
    {
        // Roles added by this call are not visible to a query until saved, so match on the returned list.
        var roles = await UserProvisioning.EnsureRoles(db, organizationId, ct);
        return roles.SingleOrDefault(x => x.Name.Equals(name, StringComparison.OrdinalIgnoreCase)) ?? throw new ArgumentException("Unknown role.");
    }

    private Task<bool> IsOwner(Guid userId, CancellationToken ct) => db.PersonRoles.Join(db.Roles, x => x.RoleId, x => x.Id, (link, role) => new { link, role }).AnyAsync(x => x.link.UserId == userId && x.role.Name == "Owner", ct);
    private async Task RevokeSessions(Guid userId, CancellationToken ct)
    {
        foreach (var device in await db.TrustedDevices.Where(x => x.UserId == userId).ToListAsync(ct))
            device.Revoked = true;
        foreach (var token in await db.RefreshTokens.Where(x => x.UserId == userId).ToListAsync(ct))
            token.Revoked = true;
    }
    private void Audit(SetupActor actor, string action, Guid id, string? detail, string? before = null)
    => db.AuditEvents.Add(new AuditEvent
    {
        OrganizationId = actor.OrganizationId,
        ActorId = actor.UserId,
        Action = action,
        Entity = id.ToString(),
        Before = before,
        After = detail,
        CorrelationId = actor.CorrelationId,
        OccuredAt = clock.UtcNow
    });

    // People and access changes join the change log beside setup and settings changes, so audit.view sees them.
    private async Task RecordHistory(SetupActor actor, Guid personId, PersonSnapshot? before, PersonSnapshot after, string reason, CancellationToken ct)
    {
        var organization = await organizations.Get(ct) ?? throw new UnauthorizedAccessException();
        organization.SettingsChanged();
        db.Set<OrganizationSettingsVersion>().Add(new(actor.OrganizationId, actor.UserId, organization.SettingsVersion, "people", personId,
            clock.UtcNow, JsonSerializer.Serialize(before), JsonSerializer.Serialize(after), reason, actor.CorrelationId));
    }

    // "role", "role and data scope", "name, role and data scope".
    private static string JoinWords(IReadOnlyList<string> words) =>
        words.Count == 1 ? words[0] : $"{string.Join(", ", words.Take(words.Count - 1))} and {words[^1]}";

    // What the change log keeps about a person: sorted, so two snapshots compare by value.
    private sealed record PersonSnapshot(string FirstName, string LastName, string Email, string PhoneNumber, string Role, bool Active,
        string ScopeMode, Guid[] CompanyIds, Guid[] VehicleIds, string[] Permissions, decimal? ApprovalLimit)
    {
        public string Name => $"{FirstName} {LastName}";

        public static PersonSnapshot Of(AccessPerson x) => new(x.Membership.FirstName, x.Membership.LastName, x.User.Email, x.User.PhoneNumber,
            x.Role.Name, x.Membership.Active, ScopeModeOf(x), [.. x.CompanyIds.Distinct().Order()], [.. x.VehicleIds.Distinct().Order()],
            [.. x.Permissions.Order(StringComparer.Ordinal)], x.Membership.ApprovalLimit);

        // Single permissions count only where they depart from the role's defaults; a role change brings its own.
        public List<string> Changes(PersonSnapshot after)
        {
            var changes = new List<string>();
            if (FirstName != after.FirstName || LastName != after.LastName) changes.Add("name");
            if (!string.Equals(Email, after.Email, StringComparison.OrdinalIgnoreCase) || PhoneNumber != after.PhoneNumber) changes.Add("sign-in details");
            if (!Role.Equals(after.Role, StringComparison.OrdinalIgnoreCase)) changes.Add("role");
            if (!Deviation.From(PermissionCatalog.DefaultsFor(Role), Permissions.ToHashSet(StringComparer.Ordinal))
                .Same(Deviation.From(PermissionCatalog.DefaultsFor(after.Role), after.Permissions.ToHashSet(StringComparer.Ordinal))))
                changes.Add("single permissions");
            if (ScopeMode != after.ScopeMode || !CompanyIds.SequenceEqual(after.CompanyIds) || !VehicleIds.SequenceEqual(after.VehicleIds)) changes.Add("data scope");
            if (ApprovalLimit != after.ApprovalLimit) changes.Add("approval limit");
            return changes;
        }
    }

    private sealed record Deviation(IReadOnlySet<string> Granted, IReadOnlySet<string> Denied)
    {
        public static readonly Deviation None = new(new HashSet<string>(), new HashSet<string>());
        public static Deviation From(IReadOnlyList<string> defaults, IReadOnlySet<string> effective) =>
            new(effective.Except(defaults).ToHashSet(StringComparer.Ordinal), defaults.Except(effective).ToHashSet(StringComparer.Ordinal));
        public bool Same(Deviation other) => Granted.SetEquals(other.Granted) && Denied.SetEquals(other.Denied);
    }

    private sealed record AccessPerson(User User, OrganizationMembership Membership, Role Role, IReadOnlySet<string> Permissions, SetupDataScope? Scope, List<Guid> CompanyIds, List<Guid> VehicleIds);
}