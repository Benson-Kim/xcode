using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;
using Xunit;
using Xunit.Abstractions;

namespace Auth.Tests;

// Setup lists are compressed when the caller accepts it; sign-in and token bodies never are.
public sealed class CompressionTests(ITestOutputHelper output) : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";

    // A change log long enough to be worth compressing: one row per save, with the whole record before and after.
    private Task AddChanges(int count) => app.WithDb(async db =>
    {
        db.Provisioning = true;
        var organization = await db.Organizations.IgnoreQueryFilters().SingleAsync();
        var actor = (await db.Users.SingleAsync(x => x.Email == Owner)).Id;
        for (var i = 0; i < count; i++)
        {
            organization.SettingsChanged();
            var vehicle = Guid.NewGuid();
            string Snapshot(decimal target) =>
                $$"""{"Id":"{{vehicle}}","Registration":"KDA {{100 + i}}A","Make":"Toyota","Model":"HiAce","Seats":14,"WeeklyTarget":{{target}},"Active":true}""";
            db.Set<OrganizationSettingsVersion>().Add(new(organization.Id, actor, organization.SettingsVersion, "vehicles", vehicle,
                app.Clock.UtcNow, Snapshot(35000), Snapshot(42000), $"Raised the weekly target for KDA {100 + i}A", "test", vehicleId: vehicle));
        }
        await db.SaveChangesAsync();
    });

    private static async Task<(HttpResponseMessage Response, byte[] Bytes)> Get(HttpClient client, string path, string? encoding)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, path);
        if (encoding is not null) request.Headers.TryAddWithoutValidation("Accept-Encoding", encoding);
        var response = await client.SendAsync(request);
        return (response, await response.Content.ReadAsByteArrayAsync());
    }

    private static byte[] Decode(string encoding, byte[] bytes)
    {
        using var input = new MemoryStream(bytes);
        using Stream decoder = encoding == "br" ? new BrotliStream(input, CompressionMode.Decompress) : new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        decoder.CopyTo(output);
        return output.ToArray();
    }

    [Theory]
    [InlineData("br", "br")]
    [InlineData("gzip", "gzip")]
    [InlineData("gzip, deflate, br", "br")]
    public async Task SetupResponsesAreCompressedInTheEncodingTheCallerAccepts(string accept, string expected)
    {
        await app.SeedDemo();
        await AddChanges(100);
        using var client = await app.SignIn(Owner);

        var (plain, plainBytes) = await Get(client, "/setup/history?pageSize=100", null);
        Assert.Equal(HttpStatusCode.OK, plain.StatusCode);
        Assert.Empty(plain.Content.Headers.ContentEncoding);

        var (compressed, bytes) = await Get(client, "/setup/history?pageSize=100", accept);
        Assert.Equal(HttpStatusCode.OK, compressed.StatusCode);
        Assert.Equal([expected], compressed.Content.Headers.ContentEncoding);
        Assert.Contains("Accept-Encoding", compressed.Headers.Vary);
        Assert.Equal(plainBytes, Decode(expected, bytes));
        Assert.True(bytes.Length < plainBytes.Length / 4, $"{bytes.Length} bytes compressed, {plainBytes.Length} plain.");
    }

    [Fact]
    public async Task EverySetupListIsCompressedAndItsSizeIsReported()
    {
        await app.SeedDemo();
        await AddChanges(100);
        using var client = await app.SignIn(Owner);

        foreach (var path in new[] { "/setup/history?pageSize=100", "/setup/people?pageSize=100", "/setup/vehicles?pageSize=100", "/setup/expense-categories?pageSize=100" })
        {
            var (_, plain) = await Get(client, path, null);
            var (brotli, br) = await Get(client, path, "br");
            var (gzipped, gzip) = await Get(client, path, "gzip");
            Assert.Equal(["br"], brotli.Content.Headers.ContentEncoding);
            Assert.Equal(["gzip"], gzipped.Content.Headers.ContentEncoding);
            Assert.Equal(plain, Decode("br", br));
            Assert.Equal(plain, Decode("gzip", gzip));
            output.WriteLine($"{path}: {plain.Length} bytes plain, {gzip.Length} gzip ({100 - 100 * gzip.Length / plain.Length}% smaller), {br.Length} brotli ({100 - 100 * br.Length / plain.Length}% smaller)");
        }
    }

    [Fact]
    public async Task AuthResponsesAreNeverCompressed()
    {
        await app.Seed();
        using var client = app.CreateClient();
        foreach (var encoding in new[] { "br", "gzip", "gzip, deflate, br" })
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, "/auth/sign-in") { Content = JsonContent.Create(new AuthRequest(PhoneNumber: "+254712345678", Pin: "5826", DeviceId: "phone")) };
            request.Headers.TryAddWithoutValidation("Accept-Encoding", encoding);
            using var response = await client.SendAsync(request);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            Assert.Empty(response.Content.Headers.ContentEncoding);
            Assert.DoesNotContain("Accept-Encoding", response.Headers.Vary);
            Assert.Contains("accessToken", await response.Content.ReadAsStringAsync());
        }
    }

    public void Dispose() => app.Dispose();
}
