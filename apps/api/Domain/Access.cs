namespace Auth.Domain;

public sealed class Role : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid Id { get; set; } = Guid.NewGuid();
     public string Name { get; set; } = "";
}


// Legacy: role defaults now come only from PermissionCatalog. Nothing reads or writes this table; it is kept until
// a later migration drops it.
public sealed class RolePermission : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid RoleId { get; set; }
     public string Permission { get; set; } = "";
}


public sealed class PersonRole : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid UserId { get; set; }
     public Guid RoleId { get; set; }
}


public sealed class PersonPermissionOverride : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid UserId { get; set; }
     public string Permission { get; set; } = "";
     public bool Granted { get; set; }
}


public sealed class AuditEvent : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid Id { get; set; } = Guid.NewGuid();
     public Guid ActorId { get; set; }
     public string Action { get; set; } = "";
     public string Entity { get; set; } = "";
     public string? Before { get; set; }
     public string? After { get; set; }
     public string CorrelationId { get; set; } = "";
     public DateTimeOffset OccuredAt { get; set; }
}


public static class PermissionDependencies
{
     // This is the one dependency graph used by the catalog, role defaults and request-time authorization.
     private static readonly IReadOnlyDictionary<string, string[]> DirectDependencies = new Dictionary<string, string[]>(StringComparer.Ordinal)
     {
          ["dash.capture"] = ["revenue.capture"],
          ["dash.float"] = ["pettycash.spend"],
          ["dash.revenue"] = ["revenue.view"],
          ["dash.net"] = ["revenue.view", "expenses.view", "commitments.view"],
          ["dash.costs"] = ["expenses.view", "commitments.view"],
          ["dash.gaps"] = ["revenue.view"],
          ["dash.pettycash"] = ["pettycash.view_all"],
          ["dash.commitments"] = ["commitments.view"],
          ["dash.investment"] = ["invest.view"],
          ["dash.edits"] = ["audit.view"],

          ["revenue.capture"] = ["revenue.view"],
          ["revenue.no_earnings"] = ["revenue.capture"],
          ["revenue.correct"] = ["revenue.view"],

          ["expenses.capture"] = ["expenses.view"],
          ["expenses.correct"] = ["expenses.view"],
          ["expenses.setup"] = ["expenses.view"],

          ["pettycash.approve_item"] = ["pettycash.view_all"],
          ["pettycash.approve_day"] = ["pettycash.approve_item"],
          ["pettycash.issue"] = ["pettycash.view_all"],
          ["pettycash.issue_negative"] = ["pettycash.issue"],

          ["bills.capture"] = ["bills.view"],
          ["bills.approve"] = ["bills.view"],

          ["commitments.manage"] = ["commitments.view"],
          ["reports.export"] = ["reports.view"],
          ["invest.manage"] = ["invest.view"],
          ["people.manage"] = ["people.view"],
          ["access.manage"] = ["people.manage"]
     };

     public static IReadOnlyList<string> DirectFor(string permission) =>
          DirectDependencies.TryGetValue(permission, out var dependencies) ? dependencies : Array.Empty<string>();

     public static IReadOnlySet<string> Expand(IEnumerable<string> permissions)
     {
          var result = permissions.ToHashSet(StringComparer.Ordinal);
          var pending = new Queue<string>(result);
          while (pending.TryDequeue(out var key))
               foreach (var dependency in DirectFor(key))
                    if (result.Add(dependency))
                         pending.Enqueue(dependency);
          return result;
     }
}


public sealed class EffectivePermissionResolver
{
     public IReadOnlySet<string> Resolve(IEnumerable<string> rolePermissions, IEnumerable<PersonPermissionOverride> overrides, bool active = true)
     {
          if (!active) return new HashSet<string>(StringComparer.Ordinal);

          var all = overrides.ToArray();
          var denied = all.Where(x => !x.Granted).Select(x => x.Permission).ToHashSet(StringComparer.Ordinal);
          var result = PermissionDependencies.Expand(rolePermissions.Concat(all.Where(x => x.Granted).Select(x => x.Permission)))
               .ToHashSet(StringComparer.Ordinal);

          // A denied permission also removes every permission that depends on it.
          result.ExceptWith(denied);

          bool changed;
          do
          {
               changed = false;
               foreach (var key in result.ToArray())
                    if (PermissionDependencies.DirectFor(key).Any(x => !result.Contains(x)))
                         changed |= result.Remove(key);
          } while (changed);

          return result;
     }
}
