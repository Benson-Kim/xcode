

using System.Security.Claims;
using Auth.Application;

namespace Auth.Infrastructure;

public sealed class organizationContext(IHttpContextAccessor accessor) : IOrganizationContext
{
     public Guid OrganizationId => Guid.TryParse(accessor.HttpContext?.User.FindFirstValue("org"), out var id) ? id : Guid.Empty;

     public Guid ActorId => Guid.TryParse(accessor.HttpContext?.User.FindFirstValue("sub"), out var id) ? id : Guid.Empty;

     public string CorrelationId => accessor.HttpContext?.TraceIdentifier ?? Guid.NewGuid().ToString();
}