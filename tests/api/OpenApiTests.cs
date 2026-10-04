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

    // The description must say what callers really get back, and how they authenticate.
    [Fact]
    public async Task TheOpenApiDocumentDescribesResponsesAndBearerAuthentication()
    {
        using var client = app.CreateClient();
        using var document = JsonDocument.Parse(await client.GetStringAsync("/openapi/v1.json"));
        var root = document.RootElement;
        var paths = root.GetProperty("paths");
        static string Schema(JsonElement operation, string status, string contentType) =>
            operation.GetProperty("responses").GetProperty(status).GetProperty("content").GetProperty(contentType).GetProperty("schema").GetProperty("$ref").GetString()!;

        var signIn = paths.GetProperty("/auth/sign-in").GetProperty("post");
        Assert.Equal("#/components/schemas/AuthResponse", Schema(signIn, "202", "application/json"));
        Assert.Equal("#/components/schemas/AuthResponse", Schema(signIn, "423", "application/json"));
        Assert.False(signIn.TryGetProperty("security", out _));

        var deactivate = paths.GetProperty("/setup/people/{id}/deactivate").GetProperty("post");
        Assert.Equal("#/components/schemas/ProblemDetails", Schema(deactivate, "409", "application/problem+json"));
        Assert.True(deactivate.GetProperty("security")[0].TryGetProperty("Bearer", out _));

        var bearer = root.GetProperty("components").GetProperty("securitySchemes").GetProperty("Bearer");
        Assert.Equal("http", bearer.GetProperty("type").GetString());
        Assert.Equal("bearer", bearer.GetProperty("scheme").GetString());
    }

    public void Dispose() => app.Dispose();
}
