using System.Net;
using System.Text.Json;
using Xunit;

namespace Auth.Tests;

public sealed class OpenApiTests : IDisposable
{
    private readonly AuthFactory app = new();

    [Fact]
    public async Task TheOpenApiDocumentIsServedInTesting()
    {
        using var client = app.CreateClient();
        using var response = await client.GetAsync("/openapi/v1.json");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var paths = document.RootElement.GetProperty("paths");
        Assert.True(paths.TryGetProperty("/auth/sign-in", out _));
        Assert.True(paths.TryGetProperty("/setup/people", out _));
    }

    public void Dispose() => app.Dispose();
}
