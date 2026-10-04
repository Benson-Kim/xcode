using Auth.Application;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.OpenApi;
using Microsoft.OpenApi;

namespace Auth.Api;

// What /openapi/v1.json says beyond each endpoint's own metadata: how callers authenticate, and one schema correction.
public static class OpenApiDocumentation
{
    public const string BearerScheme = "Bearer";

    public static void Configure(OpenApiOptions options)
    {
        options.AddDocumentTransformer((document, _, _) =>
        {
            document.AddComponent(BearerScheme, new OpenApiSecurityScheme
            {
                Type = SecuritySchemeType.Http,
                Scheme = "bearer",
                BearerFormat = "JWT",
                Description = "The access token returned by sign-in, verify-device, PIN setup or reset, and refresh.",
            });
            return Task.CompletedTask;
        });

        // An endpoint that requires authorization needs the bearer token, and without a valid one the JWT challenge
        // answers 401 with no body.
        options.AddOperationTransformer((operation, context, _) =>
        {
            var metadata = context.Description.ActionDescriptor.EndpointMetadata;
            if (!metadata.OfType<IAuthorizeData>().Any() || metadata.OfType<IAllowAnonymous>().Any())
                return Task.CompletedTask;
            operation.Security ??= [];
            operation.Security.Add(new OpenApiSecurityRequirement { [new OpenApiSecuritySchemeReference(BearerScheme, context.Document)] = [] });
            operation.Responses ??= new OpenApiResponses();
            operation.Responses.TryAdd("401", new OpenApiResponse { Description = "Unauthorized" });
            return Task.CompletedTask;
        });

        // PermissionItem.Needs is computed and never null, but the generator reads a get-only property as nullable.
        options.AddSchemaTransformer((schema, context, _) =>
        {
            if (context.JsonTypeInfo.Type == typeof(PermissionItem) && schema.Properties?.TryGetValue("needs", out var needs) == true && needs is OpenApiSchema list)
            {
                list.Type &= ~JsonSchemaType.Null;
                (schema.Required ??= new HashSet<string>()).Add("needs");
            }
            return Task.CompletedTask;
        });
    }
}
