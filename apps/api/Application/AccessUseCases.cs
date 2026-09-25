using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Application.Setup;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;

namespace Auth.Application;

public sealed class AccessUseCases(ISetupExecution execution, AuthDb db)
{
    public Task<IReadOnlyList<PermissionGroup>> Catalog(CancellationToken ct) => execution.Read("people.view", _ => Task.FromResult(PermissionCatalog.Groups), ct);

    public Task<IReadOnlyList<AccessRole>> Roles(CancellationToken ct) => execution.Read("people.view", async actor =>
    {
        await EnsureRoles(actor.OrganizationId, ct);
        return (IReadOnlyList<AccessRole>)await db.Roles.AsNoTracking().OrderBy(x => x.Name).Select(x => new AccessRole(x.Id, x.Name)).ToListAsync(ct);
    }, ct);

    public Task<Page<PersonDto>> List(int page, int pageSize, CancellationToken ct) => execution.Read("people.view", async actor =>
    {
        SetupPagination.Validate(page, pageSize);
        var people = await LoadPeople(actor, ct);
        var rows = people.OrderBy(x => x.Membership.LastName).ThenBy(x => x.Membership.FirstName).Skip((page - 1) * pageSize).Take(pageSize).Select(ToDto).ToArray();
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
        if (id is not null && target is null) throw new KeyNotFoundException();
        if (id == actor.UserId) throw new ArgumentException("You cannot change your own access here.");
        var actorIsOwner = await IsOwner(actor.UserId, ct);
        if (role.Name.Equals("Owner", StringComparison.OrdinalIgnoreCase) && !actorIsOwner) throw new UnauthorizedAccessException();
        if (target is not null && target.Role.Name.Equals("Owner", StringComparison.OrdinalIgnoreCase) && !actorIsOwner) throw new UnauthorizedAccessException();
        ValidateScope(actor, input);
        var permissions = PermissionCatalog.WithDependencies(input.Permissions);
        if (permissions.Any(x => !PermissionCatalog.All.Contains(x, StringComparer.Ordinal))) throw new ArgumentException("Unknown permission.");
        var phone = PhoneNumber.Normalize(input.PhoneNumber);
        var email = input.Email.Trim().ToLowerInvariant();
        if (await db.Users.AnyAsync(x => (x.PhoneNumber == phone || x.Email == email) && x.Id != id, ct)) throw new ArgumentException("That mobile number or email already belongs to someone.");

        if (target is null)
        {
            var user = new User { PhoneNumber = phone, Email = email };
            db.Users.Add(user);
            db.Memberships.Add(new OrganizationMembership { OrganizationId = actor.OrganizationId, UserId = user.Id, FirstName = input.FirstName.Trim(), LastName = input.LastName.Trim(), ApprovalLimit = input.ApprovalLimit });
            db.PersonRoles.Add(new PersonRole { OrganizationId = actor.OrganizationId, UserId = user.Id, RoleId = role.Id });
            ApplyScope(actor.OrganizationId, user.Id, input);
            ApplyOverrides(actor.OrganizationId, user.Id, role, permissions);
            Audit(actor, "person.created", user.Id, input.Role);
            return user.Id;
        }

        target.Membership.FirstName = input.FirstName.Trim();
        target.Membership.LastName = input.LastName.Trim();
        target.Membership.ApprovalLimit = input.ApprovalLimit;
        target.User.Email = email;
        target.User.PhoneNumber = phone;
        db.PersonRoles.RemoveRange(db.PersonRoles.Where(x => x.UserId == target.User.Id));
        db.PermissionOverrides.RemoveRange(db.PermissionOverrides.Where(x => x.UserId == target.User.Id));
        db.SetupDataScopes.RemoveRange(db.SetupDataScopes.Where(x => x.UserId == target.User.Id));
        db.SetupCompanyScopes.RemoveRange(db.SetupCompanyScopes.Where(x => x.UserId == target.User.Id));
        db.SetupVehicleScopes.RemoveRange(db.SetupVehicleScopes.Where(x => x.UserId == target.User.Id));
        db.PersonRoles.Add(new PersonRole { OrganizationId = actor.OrganizationId, UserId = target.User.Id, RoleId = role.Id });
        ApplyScope(actor.OrganizationId, target.User.Id, input);
        ApplyOverrides(actor.OrganizationId, target.User.Id, role, permissions);
        Audit(actor, "person.updated", target.User.Id, input.Role);
        return target.User.Id;
    }, ct);

    public Task<Guid> SetActive(Guid id, bool active, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        if (id == actor.UserId) throw new ArgumentException("You cannot deactivate your own access.");
        var target = (await LoadPeople(actor, ct)).SingleOrDefault(x => x.User.Id == id) ?? throw new KeyNotFoundException();
        if (active) { target.Membership.Reactivate(); target.User.Status = UserStatus.Active; }
        else { target.Membership.Deactivate(); target.User.Status = UserStatus.Removed; target.User.SecurityVersion++; await RevokeSessions(id, ct); }
        Audit(actor, active ? "person.activated" : "person.deactivated", id, null);
        return id;
    }, ct);

    public Task<Guid> SignOut(Guid id, CancellationToken ct) => execution.Write("people.manage", async actor =>
    {
        if (id == actor.UserId) throw new ArgumentException("Use sign out for your own session.");
        _ = (await LoadPeople(actor, ct)).SingleOrDefault(x => x.User.Id == id) ?? throw new KeyNotFoundException();
        await RevokeSessions(id, ct); Audit(actor, "person.sessions_revoked", id, null); return id;
    }, ct);

    private async Task<List<AccessPerson>> LoadPeople(SetupActor actor, CancellationToken ct)
    {
        var memberships = await db.Memberships.ToListAsync(ct);
        var users = await db.Users.Where(x => memberships.Select(m => m.UserId).Contains(x.Id)).ToDictionaryAsync(x => x.Id, ct);
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
            var defaults = PermissionCatalog.RolePermissions.GetValueOrDefault(role.Name, []);
            var permissions = new EffectivePermissionResolver().Resolve(defaults, overrides.Where(x => x.UserId == user.Id), membership.Active);
            result.Add(new AccessPerson(user, membership, role, permissions, scope, companyIds, vehicleIds));
        }
        return result;
    }

    private static PersonDto ToDto(AccessPerson x) => new(x.User.Id, x.Membership.FirstName, x.Membership.LastName, x.User.Email, x.User.PhoneNumber, x.Role.Name, x.Membership.Active, x.Scope?.AllCompanies == true ? "all" : x.CompanyIds.Count > 0 ? "companies" : "vehicles", x.CompanyIds, x.VehicleIds, x.Permissions.ToArray(), x.Membership.ApprovalLimit, x.User.PinHash is not null);

    private static void Validate(SavePerson input)
    {
        if (string.IsNullOrWhiteSpace(input.FirstName) || input.FirstName.Length > 100 || string.IsNullOrWhiteSpace(input.LastName) || input.LastName.Length > 100) throw new ArgumentException("First and last name are required.");
        if (!System.Net.Mail.MailAddress.TryCreate(input.Email, out _)) throw new ArgumentException("A valid email is required.");
        if (PhoneNumber.Normalize(input.PhoneNumber) == "") throw new ArgumentException("A valid mobile number is required.");
        if (input.ScopeMode is not ("all" or "companies" or "vehicles")) throw new ArgumentException("Choose a data scope.");
        if (input.ScopeMode == "companies" && input.CompanyIds.Count == 0 || input.ScopeMode == "vehicles" && input.VehicleIds.Count == 0) throw new ArgumentException("Choose at least one item in the data scope.");
        if (input.Permissions.Count == 0 || input.ApprovalLimit is < 0) throw new ArgumentException("Permissions and approval limit are invalid.");
    }

    private static void ValidateScope(SetupActor actor, SavePerson input)
    {
        if (input.ScopeMode == "all" && !actor.AllCompanies) throw new UnauthorizedAccessException();
        if (input.ScopeMode == "companies" && input.CompanyIds.Any(x => !actor.AllCompanies && !actor.CompanyIds.Contains(x))) throw new UnauthorizedAccessException();
        if (input.ScopeMode == "vehicles" && input.VehicleIds.Any(x => !actor.AllCompanies && !actor.VehicleIds.Contains(x))) throw new UnauthorizedAccessException();
    }

    private void ApplyScope(Guid organizationId, Guid userId, SavePerson input)
    {
        if (input.ScopeMode == "all") db.SetupDataScopes.Add(new SetupDataScope { OrganizationId = organizationId, UserId = userId, AllCompanies = true });
        if (input.ScopeMode == "companies") db.SetupCompanyScopes.AddRange(input.CompanyIds.Select(x => new SetupCompanyScope { OrganizationId = organizationId, UserId = userId, CompanyId = x }));
        if (input.ScopeMode == "vehicles") db.SetupVehicleScopes.AddRange(input.VehicleIds.Select(x => new SetupVehicleScope { OrganizationId = organizationId, UserId = userId, VehicleId = x }));
    }

    private void ApplyOverrides(Guid organizationId, Guid userId, Role role, IReadOnlyList<string> permissions)
    {
        var defaults = PermissionCatalog.RolePermissions.GetValueOrDefault(role.Name, []);
        db.PermissionOverrides.AddRange(PermissionCatalog.All.Where(x => defaults.Contains(x) != permissions.Contains(x)).Select(x => new PersonPermissionOverride { OrganizationId = organizationId, UserId = userId, Permission = x, Granted = permissions.Contains(x) }));
    }

    private async Task<Role> EnsureRole(string name, Guid organizationId, CancellationToken ct)
    {
        await EnsureRoles(organizationId, ct);
        return await db.Roles.SingleOrDefaultAsync(x => x.Name == name, ct) ?? throw new ArgumentException("Unknown role.");
    }

    private async Task EnsureRoles(Guid organizationId, CancellationToken ct)
    {
        var existing = await db.Roles.ToListAsync(ct);
        foreach (var pair in PermissionCatalog.RolePermissions)
            if (existing.All(x => !x.Name.Equals(pair.Key, StringComparison.OrdinalIgnoreCase)))
            {
                var role = new Role { OrganizationId = organizationId, Name = pair.Key }; db.Roles.Add(role); db.RolePermissions.AddRange(PermissionCatalog.WithDependencies(pair.Value).Select(x => role.Grant(x)));
            }
    }

    private Task<bool> IsOwner(Guid userId, CancellationToken ct) => db.PersonRoles.Join(db.Roles, x => x.RoleId, x => x.Id, (link, role) => new { link, role }).AnyAsync(x => x.link.UserId == userId && x.role.Name == "Owner", ct);
    private async Task RevokeSessions(Guid userId, CancellationToken ct)
    {
        foreach (var device in await db.TrustedDevices.Where(x => x.UserId == userId).ToListAsync(ct)) device.Revoked = true;
        foreach (var token in await db.RefreshTokens.Where(x => x.UserId == userId).ToListAsync(ct)) token.Revoked = true;
    }
    private void Audit(SetupActor actor, string action, Guid id, string? detail) => db.AuditEvents.Add(new AuditEvent { OrganizationId = actor.OrganizationId, ActorId = actor.UserId, Action = action, Entity = id.ToString(), After = detail, CorrelationId = actor.CorrelationId, OccuredAt = DateTimeOffset.UtcNow });

    private sealed record AccessPerson(User User, OrganizationMembership Membership, Role Role, IReadOnlySet<string> Permissions, SetupDataScope? Scope, List<Guid> CompanyIds, List<Guid> VehicleIds);
}