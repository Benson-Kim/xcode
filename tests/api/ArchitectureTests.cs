using System.Reflection;
using Auth.Application;
using Auth.Infrastructure;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Auth.Tests;

// Endpoints route and translate HTTP only. The database, the clock and the organization repository belong to the use
// cases, which run authorization, the transaction and the change-log retry around them.
public sealed class ArchitectureTests : IDisposable
{
    private readonly AuthFactory app = new();
    static readonly string[] Exempt = [];
    private static readonly Type[] UseCaseOnly = [typeof(DbContext), typeof(IClock), typeof(IOrganizationRepository)];

    private static IEnumerable<string> Offences(MethodInfo handler) => handler.GetParameters()
        .Where(parameter => UseCaseOnly.Any(type => type.IsAssignableFrom(parameter.ParameterType)))
        .Select(parameter => $"{parameter.ParameterType.Name} {parameter.Name}");

    [Fact]
    public void EndpointsDoNotTakeTheDatabase()
    {
        var handlers = app.Services.GetRequiredService<EndpointDataSource>().Endpoints.OfType<RouteEndpoint>()
            .Select(endpoint => (Route: endpoint.RoutePattern.RawText ?? "", Handler: endpoint.Metadata.GetMetadata<MethodInfo>()))
            .Where(x => x.Handler is not null)
            .ToList();

        // A scan that finds nothing proves nothing: it sees every API handler, the settings ones included, and it
        // recognises a handler that does take the database.
        Assert.True(handlers.Count > 40, $"Only {handlers.Count} endpoint handlers were found.");
        Assert.Contains(handlers, x => x.Route == "/setup/organization/settings/{section}");
        Assert.Equal(["AuthDb db", "IClock clock"], Offences(((Func<AuthDb, IClock, IResult>)((db, clock) => Results.Ok())).Method));

        Assert.Empty(handlers
            .Where(x => !Exempt.Any(prefix => x.Route.StartsWith(prefix, StringComparison.Ordinal)))
            .SelectMany(x => Offences(x.Handler!).Select(offence => $"{x.Route} takes {offence}")));
    }

    public void Dispose() => app.Dispose();
}
