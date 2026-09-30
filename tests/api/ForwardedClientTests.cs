using System.Net;
using System.Net.Http.Json;
using Auth.Application;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Auth.Tests;

// Every web sign-in reaches the API from the Next.js proxy, which names the browser in X-Forwarded-For. The sign-in rate
// limit must count each browser on its own, and believe that header only from a trusted proxy (loopback unless
// ForwardedHeaders:KnownProxies says otherwise), or anyone could pick a fresh address for every try.
public sealed class ForwardedClientTests : IDisposable
{
    private readonly AuthFactory app = new();
    private WebApplicationFactory<Program>? host;

    [Theory]
    [InlineData("127.0.0.1")]
    [InlineData("::1")]
    [InlineData("::ffff:127.0.0.1")]
    public async Task EachBrowserBehindTheLocalProxyHasItsOwnLimit(string proxy)
    {
        using var client = await Client();
        Assert.Equal([HttpStatusCode.Unauthorized, HttpStatusCode.Unauthorized, HttpStatusCode.TooManyRequests],
            [await SignIn(client, proxy, "198.51.100.7"), await SignIn(client, proxy, "198.51.100.7"), await SignIn(client, proxy, "198.51.100.7")]);
        Assert.Equal(HttpStatusCode.Unauthorized, await SignIn(client, proxy, "198.51.100.8"));
    }

    [Fact]
    public async Task AForwardedAddressFromAnyoneElseIsIgnored()
    {
        using var client = await Client();
        // A caller that is not a trusted proxy cannot claim a new address for each try.
        Assert.Equal([HttpStatusCode.Unauthorized, HttpStatusCode.Unauthorized, HttpStatusCode.TooManyRequests],
            [await SignIn(client, "203.0.113.9", "198.51.100.7"), await SignIn(client, "203.0.113.9", "198.51.100.8"), await SignIn(client, "203.0.113.9", "198.51.100.9")]);
        // The limit is that caller's own: another caller is not held up by it.
        Assert.Equal(HttpStatusCode.Unauthorized, await SignIn(client, "203.0.113.10", "198.51.100.7"));
    }

    [Fact]
    public async Task ConfiguredProxiesReplaceLoopback()
    {
        using var client = await Client(("ForwardedHeaders:KnownProxies:0", "10.0.0.5"));
        Assert.Equal(HttpStatusCode.Unauthorized, await SignIn(client, "10.0.0.5", "198.51.100.7"));
        Assert.Equal(HttpStatusCode.Unauthorized, await SignIn(client, "10.0.0.5", "198.51.100.7"));
        Assert.Equal(HttpStatusCode.Unauthorized, await SignIn(client, "10.0.0.5", "198.51.100.8"));
        // Loopback is no longer trusted, so its forwarded addresses all count as loopback's own tries.
        Assert.Equal(HttpStatusCode.Unauthorized, await SignIn(client, "127.0.0.1", "198.51.100.9"));
        Assert.Equal(HttpStatusCode.Unauthorized, await SignIn(client, "127.0.0.1", "198.51.100.10"));
        Assert.Equal(HttpStatusCode.TooManyRequests, await SignIn(client, "127.0.0.1", "198.51.100.11"));
    }

    // A host allowing two sign-in tries a minute, whose requests arrive from the address in X-Test-Remote-Address.
    private async Task<HttpClient> Client(params (string Key, string Value)[] settings)
    {
        host = app.WithWebHostBuilder(builder =>
        {
            builder.UseSetting("RateLimiting:AuthPermitLimit", "2");
            foreach (var (key, value) in settings) builder.UseSetting(key, value);
            builder.ConfigureServices(services => services.AddSingleton<IStartupFilter, RemoteAddressFromHeader>());
        });
        await app.WithDb(db => db.Database.EnsureCreatedAsync());
        return host.CreateClient();
    }

    private static async Task<HttpStatusCode> SignIn(HttpClient client, string remoteAddress, string forwardedFor)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/auth/sign-in")
        {
            Content = JsonContent.Create(new AuthRequest(PhoneNumber: "+254700000000", Pin: "5826", DeviceId: "browser"))
        };
        request.Headers.Add("X-Test-Remote-Address", remoteAddress);
        request.Headers.Add("X-Forwarded-For", forwardedFor);
        using var response = await client.SendAsync(request);
        return response.StatusCode;
    }

    // The test server has no socket, so it leaves the remote address empty; this stands in for the connection's address.
    private sealed class RemoteAddressFromHeader : IStartupFilter
    {
        public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
        {
            app.Use((context, then) =>
            {
                if (IPAddress.TryParse(context.Request.Headers["X-Test-Remote-Address"].ToString(), out var address))
                    context.Connection.RemoteIpAddress = address;
                return then(context);
            });
            next(app);
        };
    }

    public void Dispose()
    {
        host?.Dispose();
        app.Dispose();
    }
}
