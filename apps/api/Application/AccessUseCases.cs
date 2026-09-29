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

    // A write, although it only lists roles: EnsureRoles may add a catalog role the organization is missing.
    public Task<IReadOnlyList<AccessRole>> Roles(CancellationToken ct) => execution.Write("people.view", async actor =>
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
            .Where(v => actor.AllCompanies || actor.VehicleIds.Contains(v.Id) || actor.CompanyIds.Contains(v.CompanyId))
            .OrderBy(v => v.Registration)
            .Select(v => new ScopeVehicleOption(v.Id, v.Registration, v.CompanyId))
            .ToListAsync(ct);
        return new ScopeOptions(companies, vehicles);
    }, ct);

    // Visibility, order and paging run in the database; only the page's own related rows are loaded.
    public Task<Page<PersonDto>> List(int page, int pageSize, CancellationToken ct) => execution.Read("people.view", async actor =>
    {
        SetupPagination.Validate(page, pageSize);
        var visible = Visible(actor);
        var total = await visible.CountAsync(ct);
        var rows = await Load(visible
            .OrderBy(x => x.LastName)
            .ThenBy(x => x.FirstName)
            .ThenBy(x => x.UserId)
            .Skip((page - 1) * pageSize)
            .Take(pageSize), ct);
        return new Page<PersonDto>(rows.Select(ToDto).ToArray(), page, pageSize, total);
    }, ct);

    public Task<PersonDto> Get(Guid id, CancellationToken ct) => execution.Read("people.view", async actor =>
        ToDto(await LoadPerson(actor, id, ct) ?? throw new KeyNotFoundException()), ct);

    public Task<Guid> Save(Guid? id, SavePerson input, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        Validate(input);
        var role = await EnsureRole(input.Role, actor.OrganizationId, ct);
        var target = id is null ? null : await LoadPerson(actor, id.Value, ct);

        if (id is not null && target is null)
            throw new KeyNotFoundException();
        if (target is not null && input.Version is null)
            throw new ArgumentException("Reload this person before saving.");
        if (target is not null && input.Version != target.Membership.Version)
            throw new DbUpdateConcurrencyException("This person's access changed. Reload before saving.");

        var payload = await PreserveHiddenScope(actor, target, input, ct);
        await ValidateScope(actor, target, payload, ct);
        if (id == actor.UserId)
            throw new ArgumentException("You cannot change your own access here.");

        var actorIsOwner = await IsOwner(actor.UserId, ct);
        if (IsOwnerRole(role) && !actorIsOwner)
            throw new UnauthorizedAccessException("Only an Owner can give the Owner role.");
        if (target is not null)
            await EnsureMayManage(actor, target, ct);

        var permissions = PermissionCatalog.WithDependencies(payload.Permissions);
        if (permissions.Any(x => !PermissionCatalog.All.Contains(x, StringComparer.Ordinal)))
            throw new ArgumentException("Unknown permission.");

        await AuthorizeAccessChange(actor, target, role, permissions, payload.ApprovalLimit, actorIsOwner, ct);
        var phone = PhoneNumber.Normalize(payload.PhoneNumber);
        var email = payload.Email.Trim().ToLowerInvariant();
        var before = target is null ? null : PersonSnapshot.Of(target);
        var after = new PersonSnapshot(payload.FirstName.Trim(), payload.LastName.Trim(), email, phone, role.Name, target?.Membership.Active ?? true,
            payload.ScopeMode, payload.ScopeMode == "companies" ? [.. payload.CompanyIds.Distinct().Order()] : [],
            payload.ScopeMode == "vehicles" ? [.. payload.VehicleIds.Distinct().Order()] : [],
            [.. Effective(role, permissions).Order(StringComparer.Ordinal)], payload.ApprovalLimit);
        var signInDetailsChanged = target is not null &&
            (!string.Equals(target.User.Email, email, StringComparison.OrdinalIgnoreCase) || target.User.PhoneNumber != phone);
        if (signInDetailsChanged)
            await AuthorizeSignInDetailsChange(actor, target!, actorIsOwner, ct);
        if (await db.Users.AnyAsync(x => (x.PhoneNumber == phone || x.Email == email) && x.Id != (id ?? Guid.Empty), ct))
            throw new ArgumentException("That mobile number or email already belongs to someone.");

        if (target is null)
        {
            var user = new User { PhoneNumber = phone, Email = email };
            db.Users.Add(user);
            db.Memberships.Add(new OrganizationMembership
            {
                OrganizationId = actor.OrganizationId,
                UserId = user.Id,
                FirstName = payload.FirstName.Trim(),
                LastName = payload.LastName.Trim(),
                ApprovalLimit = payload.ApprovalLimit
            });
            db.PersonRoles.Add(new PersonRole
            {
                OrganizationId = actor.OrganizationId,
                UserId = user.Id,
                RoleId = role.Id
            });
            ApplyScope(actor.OrganizationId, user.Id, payload);
            ApplyOverrides(actor.OrganizationId, user.Id, role, permissions);
            Audit(actor, "person.created", user.Id, JsonSerializer.Serialize(after));
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
        target.Membership.FirstName = payload.FirstName.Trim();
        target.Membership.LastName = payload.LastName.Trim();
        target.Membership.ApprovalLimit = payload.ApprovalLimit;
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
        ApplyScope(actor.OrganizationId, target.User.Id, payload);
        ApplyOverrides(actor.OrganizationId, target.User.Id, role, permissions);
        var changes = before!.Changes(after);
        if (changes.Count > 0)
        {
            target.Membership.AccessChanged();
            Audit(actor, "person.updated", target.User.Id, JsonSerializer.Serialize(after), JsonSerializer.Serialize(before));
            // Their access token carries their name, role and permissions. Bumping the version makes it fail on the next
            // request, and the client renews it with the new values, so the person is not signed out. Data scope is
            // checked against the database on every request, so it needs no renewal.
            if (changes.Intersect(["name", "role", "single permissions"]).Any())
                target.User.SecurityVersion++;
            await RecordHistory(actor, target.User.Id, before, after, $"Changed {JoinWords(changes)} for {after.Name}", ct);
        }
        return target.User.Id;
    }, ct);

    public Task<Guid> SetActive(Guid id, bool active, PersonLifecycleRequest? input, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        input ??= new();
        if (id == actor.UserId)
            throw new ArgumentException("You cannot deactivate your own access.");
        var target = await LoadPerson(actor, id, ct) ?? throw new KeyNotFoundException();
        await EnsureMayManage(actor, target, ct);
        var before = PersonSnapshot.Of(target);

        // Repeating an already-completed transition is harmless and does not require a stale form version.
        if (before.Active == active)
            return id;
        if (input.Version is null || input.Version != target.Membership.Version)
            throw new DbUpdateConcurrencyException("This person's access changed. Reload before saving.");

        var reason = active
            ? $"Restored access for {before.Name}"
            : SetupPagination.Reason(input.Reason);

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

        await RecordHistory(actor, id, before, before with { Active = active }, reason, ct);
        Audit(actor, active ? "person.activated" : "person.deactivated", id, reason);
        return id;
    }, ct);

    public Task<Guid> SignOut(Guid id, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        if (id == actor.UserId)
            throw new ArgumentException("Use sign out for your own session.");
        var target = await LoadPerson(actor, id, ct) ?? throw new KeyNotFoundException();
        await EnsureMayManage(actor, target, ct);
        await RevokeSessions(id, ct);
        Audit(actor, "person.sessions_revoked", id, null);
        var snapshot = PersonSnapshot.Of(target);
        await RecordHistory(actor, id, snapshot, snapshot, $"Signed {snapshot.Name} out of every device", ct);
        return id;
    }, ct);

    // The people the actor may see, as a query, so filtering, ordering and paging run in the database. Visible are the
    // actor themself; everyone, for an all-companies actor; anyone whose company scope meets the actor's companies or
    // the companies of the actor's vehicles; and anyone whose vehicle scope holds a vehicle the actor can see
    // (CanSeeVehicle). People without a role are never listed.
    private IQueryable<OrganizationMembership> Visible(SetupActor actor)
    {
        var people = db.Memberships.Where(m => db.PersonRoles.Any(r => r.UserId == m.UserId));
        if (actor.AllCompanies)
            return people;

        var companyIds = actor.CompanyIds.ToList();
        var vehicleIds = actor.VehicleIds.ToList();
        var vehicles = db.Set<FleetVehicle>();
        var companiesOfActorVehicles = vehicles.Where(v => vehicleIds.Contains(v.Id)).Select(v => v.CompanyId);
        var visibleVehicles = vehicles.Where(v => vehicleIds.Contains(v.Id) || companyIds.Contains(v.CompanyId)).Select(v => v.Id);
        return people.Where(m =>
            m.UserId == actor.UserId ||
            db.SetupCompanyScopes.Any(s => s.UserId == m.UserId && (companyIds.Contains(s.CompanyId) || companiesOfActorVehicles.Contains(s.CompanyId))) ||
            db.SetupVehicleScopes.Any(s => s.UserId == m.UserId && visibleVehicles.Contains(s.VehicleId)));
    }

    private async Task<AccessPerson?> LoadPerson(SetupActor actor, Guid id, CancellationToken ct) =>
        (await Load(Visible(actor).Where(x => x.UserId == id), ct)).SingleOrDefault();

    // Loads these memberships and only their own related rows: one query per table, whatever the organization's size.
    private async Task<List<AccessPerson>> Load(IQueryable<OrganizationMembership> query, CancellationToken ct)
    {
        var memberships = await query.ToListAsync(ct);
        if (memberships.Count == 0)
            return [];

        var ids = memberships.Select(x => x.UserId).ToList();
        var users = await db.Users.Where(x => ids.Contains(x.Id)).ToDictionaryAsync(x => x.Id, ct);
        var roles = (await db.PersonRoles
                .Where(x => ids.Contains(x.UserId))
                .Join(db.Roles, link => link.RoleId, role => role.Id, (link, role) => new { link.UserId, Role = role })
                .ToListAsync(ct))
            .ToLookup(x => x.UserId, x => x.Role);
        var overrides = (await db.PermissionOverrides.Where(x => ids.Contains(x.UserId)).ToListAsync(ct)).ToLookup(x => x.UserId);
        var dataScopes = (await db.SetupDataScopes.Where(x => ids.Contains(x.UserId)).ToListAsync(ct)).ToLookup(x => x.UserId);
        var companyScopes = (await db.SetupCompanyScopes.Where(x => ids.Contains(x.UserId)).ToListAsync(ct)).ToLookup(x => x.UserId, x => x.CompanyId);
        var vehicleScopes = (await db.SetupVehicleScopes.Where(x => ids.Contains(x.UserId)).ToListAsync(ct)).ToLookup(x => x.UserId, x => x.VehicleId);

        var result = new List<AccessPerson>(memberships.Count);
        foreach (var membership in memberships)
        {
            if (!users.TryGetValue(membership.UserId, out var user) || roles[user.Id].SingleOrDefault() is not { } role) continue;

            // Assigned permissions are retained for inactive people so an editor can restore them without losing configuration.
            var permissions = new EffectivePermissionResolver()
                .Resolve(PermissionCatalog.DefaultsFor(role.Name), overrides[user.Id]);
            result.Add(new AccessPerson(user, membership, role, permissions, dataScopes[user.Id].SingleOrDefault(),
                [.. companyScopes[user.Id]], [.. vehicleScopes[user.Id]]));
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
        x.User.PinHash is not null,
        x.Membership.Version
    );

    private static void Validate(SavePerson input)
    {
        var firstName = input.FirstName?.Trim() ?? "";
        var lastName = input.LastName?.Trim() ?? "";
        var email = input.Email?.Trim() ?? "";
        var companyIds = input.CompanyIds ?? [];
        var vehicleIds = input.VehicleIds ?? [];
        var permissions = input.Permissions ?? [];

        if (firstName.Length is 0 or > 100 || lastName.Length is 0 or > 100)
            throw new ArgumentException("First and last name are required.");
        if (email.Length > 320 || !System.Net.Mail.MailAddress.TryCreate(email, out _))
            throw new ArgumentException("A valid email is required.");
        if (PhoneNumber.Normalize(input.PhoneNumber ?? "") == "")
            throw new ArgumentException("A valid mobile number is required.");
        if (input.ScopeMode is not ("all" or "companies" or "vehicles"))
            throw new ArgumentException("Choose a data scope.");
        if ((input.ScopeMode == "companies" && companyIds.Count == 0) ||
            (input.ScopeMode == "vehicles" && vehicleIds.Count == 0))
            throw new ArgumentException("Choose at least one item in the data scope.");
        if (companyIds.Count != companyIds.Distinct().Count() || vehicleIds.Count != vehicleIds.Distinct().Count())
            throw new ArgumentException("Data scope items must be distinct.");
        if (permissions.Count == 0 || permissions.Count != permissions.Distinct(StringComparer.Ordinal).Count() || input.ApprovalLimit is < 0)
            throw new ArgumentException("Permissions and approval limit are invalid.");
    }

    private async Task ValidateScope(SetupActor actor, AccessPerson? target, SavePerson input, CancellationToken ct)
    {
        if (input.ScopeMode == "all" && !actor.AllCompanies)
            throw new UnauthorizedAccessException("Only someone who can see every company can give access to every company.");

        if (input.ScopeMode == "companies")
        {
            var ids = (input.CompanyIds ?? []).ToArray();
            var existing = await db.Set<PsvCompany>()
                .Where(x => ids.Contains(x.Id))
                .Select(x => x.Id)
                .ToListAsync(ct);
            if (existing.Count != ids.Length)
                throw new ArgumentException("Choose companies in your organization.");

            var retainedOutsideScope = target?.CompanyIds
                .Where(x => !actor.CompanyIds.Contains(x))
                .ToHashSet() ?? [];
            if (!actor.AllCompanies && ids.Any(x => !actor.CompanyIds.Contains(x) && !retainedOutsideScope.Contains(x)))
                throw new UnauthorizedAccessException("You can only give access to companies in your own data scope.");
        }

        if (input.ScopeMode == "vehicles")
        {
            var ids = (input.VehicleIds ?? []).ToArray();
            var existing = await db.Set<FleetVehicle>()
                .Where(x => ids.Contains(x.Id))
                .Select(x => new { x.Id, x.CompanyId })
                .ToListAsync(ct);
            if (existing.Count != ids.Length)
                throw new ArgumentException("Choose vehicles in your organization.");

            var retainedOutsideScope = target is null
                ? []
                : (await db.Set<FleetVehicle>()
                    .AsNoTracking()
                    .Where(x => target.VehicleIds.Contains(x.Id))
                    .Select(x => new { x.Id, x.CompanyId })
                    .ToListAsync(ct))
                    .Where(x => !CanSeeVehicle(actor, x.Id, x.CompanyId))
                    .Select(x => x.Id)
                    .ToHashSet();

            if (!actor.AllCompanies && existing.Any(x => !CanSeeVehicle(actor, x.Id, x.CompanyId) && !retainedOutsideScope.Contains(x.Id)))
                throw new UnauthorizedAccessException("You can only give access to vehicles in your own data scope.");
        }
    }

    private async Task<SavePerson> PreserveHiddenScope(SetupActor actor, AccessPerson? target, SavePerson input, CancellationToken ct)
    {
        if (target is null || actor.AllCompanies)
            return input;

        var hiddenCompanies = target.CompanyIds.Where(x => !actor.CompanyIds.Contains(x)).ToArray();
        var hiddenVehicles = (await db.Set<FleetVehicle>()
                .AsNoTracking()
                .Where(x => target.VehicleIds.Contains(x.Id))
                .Select(x => new { x.Id, x.CompanyId })
                .ToListAsync(ct))
            .Where(x => !CanSeeVehicle(actor, x.Id, x.CompanyId))
            .Select(x => x.Id)
            .ToArray();

        if (hiddenCompanies.Length == 0 && hiddenVehicles.Length == 0)
            return input;

        if (!string.Equals(ScopeModeOf(target), input.ScopeMode, StringComparison.Ordinal))
            throw new UnauthorizedAccessException("This person's data scope includes companies or vehicles outside your own, so you cannot change which kind of scope they have. Their companies and vehicles outside your view are kept as they are.");

        return input with
        {
            CompanyIds = input.ScopeMode == "companies"
                ? (input.CompanyIds ?? []).Concat(hiddenCompanies).Distinct().ToList()
                : input.CompanyIds ?? [],
            VehicleIds = input.ScopeMode == "vehicles"
                ? (input.VehicleIds ?? []).Concat(hiddenVehicles).Distinct().ToList()
                : input.VehicleIds ?? []
        };
    }

    private static bool CanSeeVehicle(SetupActor actor, Guid vehicleId, Guid companyId) =>
        actor.AllCompanies || actor.VehicleIds.Contains(vehicleId) || actor.CompanyIds.Contains(companyId);

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

    // people.manage covers role and scope only when the resulting role can be granted by the editor.
    // Deviations from a role and approval limits require access.manage.
    private async Task AuthorizeAccessChange(SetupActor actor, AccessPerson? target, Role role, IReadOnlyList<string> permissions, decimal? approvalLimit, bool actorIsOwner, CancellationToken ct)
    {
        var before = target is null ? Deviation.None : Deviation.From(PermissionCatalog.DefaultsFor(target.Role.Name), target.Permissions);
        var after = Deviation.From(PermissionCatalog.DefaultsFor(role.Name), Effective(role, permissions));
        var held = await organizations.Permissions(actor.UserId, ct);
        var roleChanges = target is null || !role.Name.Equals(target.Role.Name, StringComparison.OrdinalIgnoreCase);

        // A non-owner may only assign a role whose complete standard permission set they already hold (addendum 1,
        // section 2), on create and on a role change. Only an Owner gives Owner: see Save.
        if (!actorIsOwner && roleChanges && PermissionCatalog.DefaultsFor(role.Name).Any(x => !held.Contains(x)))
            throw new UnauthorizedAccessException("You can only grant roles whose permissions you hold.");

        if (after.Same(before) && approvalLimit == target?.Membership.ApprovalLimit)
            return;

        if (actorIsOwner)
            return;
        if (!held.Contains("access.manage"))
            throw new UnauthorizedAccessException("Changing single permissions or an approval limit needs \"Change single permissions and approval limits for a person\".");
        if (after.Granted.Except(before.Granted).Any(x => !held.Contains(x)))
            throw new UnauthorizedAccessException("You can only grant permissions you hold.");
    }

    // Only an Owner may edit, deactivate or sign out an Owner.
    private async Task EnsureMayManage(SetupActor actor, AccessPerson target, CancellationToken ct)
    {
        if (IsOwnerRole(target.Role) && !await IsOwner(actor.UserId, ct))
            throw new UnauthorizedAccessException("Only an Owner can change, remove or sign out an Owner.");
    }

    // Sign-in codes go to the person's email, so whoever sets their email and mobile can sign in as them. That is
    // only allowed for someone who could have granted them everything they hold anyway: an Owner, or an editor
    // whose own permissions and assignable roles cover all of the person's (and, for an approval limit, access.manage).
    private async Task AuthorizeSignInDetailsChange(SetupActor actor, AccessPerson target, bool actorIsOwner, CancellationToken ct)
    {
        if (actorIsOwner)
            return;

        var held = await organizations.Permissions(actor.UserId, ct);
        if (target.Permissions.Any(x => !held.Contains(x)) ||
            (target.Membership.ApprovalLimit is not null && !held.Contains("access.manage")))
            throw new UnauthorizedAccessException("Only an Owner, or someone who holds everything this person holds, can change their email or mobile number.");
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