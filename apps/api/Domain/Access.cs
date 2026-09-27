namespace Auth.Domain;

public sealed class Role : IOrganizationEntity
{
     public Guid OrganizationId { get; set; }
     public Guid Id { get; set; } = Guid.NewGuid();
     public string Name { get; set; } = "";
     public RolePermission Grant(string permission) => new()
     {
          OrganizationId = OrganizationId,
          RoleId = Id,
          Permission = permission
     };
}


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


public sealed class EffectivePermissionResolver
{
     public static readonly IReadOnlyDictionary<string, string[]> Dependencies = new Dictionary<string, string[]>
     {
          ["people.view"] = [],
          ["people.manage"] = ["people.view"],
          ["access.manage"] = ["people.manage"],
          ["settings.manage"] = [],
          ["audit.view"] = []
     };
     public IReadOnlySet<string> Resolve(IEnumerable<string> rolePermissions, IEnumerable<PersonPermissionOverride> overrides, bool active = true)
     {
          if (!active) return new HashSet<string>();

          var all = overrides.ToArray();
          var denied = all.Where(x => !x.Granted).Select(x => x.Permission).ToHashSet(StringComparer.Ordinal);
          var result = rolePermissions.Concat(all.Where(x => x.Granted).Select(x => x.Permission)).ToHashSet(StringComparer.Ordinal);

          var queue = new Queue<string>(result);
          while (queue.TryDequeue(out var key))
               foreach (var dependency in Dependencies.GetValueOrDefault(key) ?? [])
                    if (result.Add(dependency))
                         queue.Enqueue(dependency);

          result.ExceptWith(denied);

          bool changed;
          do
          {
               changed = false;
               foreach (var key in result.ToArray())
                    if ((Dependencies.GetValueOrDefault(key) ?? []).Any(x => !result.Contains(x)))
                         changed |= result.Remove(key);
          } while (changed);
          return result;
     }
}