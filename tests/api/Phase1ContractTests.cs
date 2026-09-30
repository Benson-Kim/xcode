using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Auth.Tests;

// Phase 1 clients already in people's hands were built from develop (0653bd1). What they send and read comes from
// develop's own code, not from this branch: packages/shared/src/index.ts (AuthResponse, createAuthClient),
// apps/mobile/src/lib/api.ts, session.ts, appearance.ts, lib/format.ts and shell/*, apps/web/lib/*,
// apps/web/app/api/{auth,setup}/[...path]/route.ts and the develop web components that call /setup/*.
// Every check reads the raw JSON, so a property that is renamed, re-cased, removed or retyped fails here, as does a
// changed status code. New properties are fine.
internal enum J { Str, Num, Bool, Null, Arr, Obj }

internal static class Phase1
{
    // Property lookup on JsonElement is ordinal, so "UserId" does not satisfy "userId".
    public static JsonElement Has(JsonElement parent, string name, params J[] kinds)
    {
        Assert.True(parent.ValueKind == JsonValueKind.Object, $"Expected an object holding \"{name}\", got {parent.ValueKind}: {parent}");
        Assert.True(parent.TryGetProperty(name, out var value), $"\"{name}\" is missing (names are case-sensitive) in {parent}");
        Assert.True(kinds.Any(kind => Is(value, kind)), $"\"{name}\" should be {string.Join(" or ", kinds)} but is {value.ValueKind}: {value}");
        return value;
    }

    private static bool Is(JsonElement value, J kind) => kind switch
    {
        J.Str => value.ValueKind == JsonValueKind.String,
        J.Num => value.ValueKind == JsonValueKind.Number,
        J.Bool => value.ValueKind is JsonValueKind.True or JsonValueKind.False,
        J.Null => value.ValueKind == JsonValueKind.Null,
        J.Arr => value.ValueKind == JsonValueKind.Array,
        J.Obj => value.ValueKind == JsonValueKind.Object,
        _ => false
    };

    public static JsonElement[] Items(JsonElement parent, string name) =>
        Has(parent, name, J.Arr).EnumerateArray().ToArray();

    public static void Strings(JsonElement parent, string name)
    {
        foreach (var item in Items(parent, name))
            Assert.True(item.ValueKind == JsonValueKind.String, $"\"{name}\" should hold strings, found {item.ValueKind}: {item}");
    }

    // A paged list as apps/web/lib/types.ts Page<T> reads it.
    public static JsonElement[] Page(JsonElement page)
    {
        Has(page, "pageNumber", J.Num);
        Has(page, "pageSize", J.Num);
        Has(page, "total", J.Num);
        return Items(page, "items");
    }

    // The problem body develop's clients show: body.detail || body.title.
    public static void Problem(JsonElement body)
    {
        Has(body, "title", J.Str);
        if (body.TryGetProperty("detail", out var detail))
            Assert.True(detail.ValueKind is JsonValueKind.String or JsonValueKind.Null, $"\"detail\" should be a string: {body}");
    }

    public static StringContent Json(object body) => new(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");

    // An empty body parses as Undefined, which is what createAuthClient's .json().catch(...) falls back from.
    public static async Task<JsonElement> Body(HttpResponseMessage response)
    {
        var text = await response.Content.ReadAsStringAsync();
        return string.IsNullOrWhiteSpace(text) ? default : JsonSerializer.Deserialize<JsonElement>(text);
    }

    public static string Date(DateOnly date) => date.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
}

public sealed class Phase1AuthContractTests : IDisposable
{
    private readonly AuthFactory app = new();
    private readonly HttpClient client;
    // What normalisePhone (apps/mobile/src/lib/phone.ts) leaves for +254 712 345 678.
    private const string Phone = "0712345678";
    private const string Address = "person@example.com";
    // The phone's id is Crypto.randomUUID() (apps/mobile/src/lib/storage.ts); the web's is crypto.randomUUID().
    private readonly string device = Guid.NewGuid().ToString();

    public Phase1AuthContractTests() => client = app.CreateClient();
    private VerificationMailer Mailer => app.Services.GetRequiredService<VerificationMailer>();

    private async Task SeedTrustedPhone(bool withPin = true)
    {
        await app.Seed(withPin, trusted: false);
        await app.WithDb(async db =>
        {
            db.TrustedDevices.Add(new() { UserId = (await db.Users.SingleAsync()).Id, DeviceId = device });
            await db.SaveChangesAsync();
        });
    }

    // apps/mobile/src/lib/api.ts authApi: every field is sent, blank when the call does not use it. The web proxy
    // (apps/web/app/api/auth/[...path]/route.ts) sends the same six fields.
    private object Request(string pin = "", string code = "", string refreshToken = "", string? deviceId = null, string phoneNumber = Phone) =>
        new { email = "", phoneNumber, pin, code, deviceId = deviceId ?? device, refreshToken };

    private async Task<(HttpStatusCode Status, JsonElement Body)> Post(string operation, object body, string? bearer = null)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/auth/" + operation) { Content = Phase1.Json(body) };
        if (bearer is not null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
        using var response = await client.SendAsync(request);
        // Setup and reset codes go out after the reply.
        await Mailer.Idle();
        return (response.StatusCode, await Phase1.Body(response));
    }

    private async Task<(HttpStatusCode Status, JsonElement Body)> Get(string path, string? bearer)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, path);
        if (bearer is not null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
        using var response = await client.SendAsync(request);
        return (response.StatusCode, await Phase1.Body(response));
    }

    // packages/shared AuthResponse. Develop always wrote all seven properties, nulls included; the web proxy copies
    // status, retryAfterSeconds, developmentCode, maskedEmail and minimumPinLength by name and keeps both tokens.
    private static void AuthBody(JsonElement body, string status)
    {
        Assert.Equal(status, Phase1.Has(body, "status", J.Str).GetString());
        Phase1.Has(body, "accessToken", J.Str, J.Null);
        Phase1.Has(body, "refreshToken", J.Str, J.Null);
        Phase1.Has(body, "retryAfterSeconds", J.Num, J.Null);
        Phase1.Has(body, "developmentCode", J.Str, J.Null);
        Phase1.Has(body, "maskedEmail", J.Str, J.Null);
        Phase1.Has(body, "minimumPinLength", J.Num, J.Null);
    }

    // keepSession stores both tokens; the web proxy reads the access token's exp for its cookie lifetime.
    private static (string Access, string Refresh) Authenticated((HttpStatusCode Status, JsonElement Body) result)
    {
        Assert.True(result.Status == HttpStatusCode.OK, $"Expected 200 authenticated, got {(int)result.Status}: {result.Body}");
        AuthBody(result.Body, "authenticated");
        var access = Phase1.Has(result.Body, "accessToken", J.Str).GetString()!;
        var refresh = Phase1.Has(result.Body, "refreshToken", J.Str).GetString()!;
        Assert.NotEmpty(refresh);
        var parts = access.Split('.');
        Assert.Equal(3, parts.Length);
        var payload = parts[1].Replace('-', '+').Replace('_', '/');
        payload = payload.PadRight(payload.Length + (4 - payload.Length % 4) % 4, '=');
        Phase1.Has(JsonSerializer.Deserialize<JsonElement>(Convert.FromBase64String(payload)), "exp", J.Num);
        return (access, refresh);
    }

    private static void Failed((HttpStatusCode Status, JsonElement Body) result, HttpStatusCode status = HttpStatusCode.Unauthorized, string body = "authentication_failed")
    {
        Assert.True(result.Status == status, $"Expected {(int)status} {body}, got {(int)result.Status}: {result.Body}");
        AuthBody(result.Body, body);
    }

    [Fact]
    public async Task SignInAndUnlockOnATrustedPhone()
    {
        await SeedTrustedPhone();
        foreach (var operation in new[] { "sign-in", "unlock" })
        {
            Authenticated(await Post(operation, Request(pin: "5826")));
            // A wrong PIN is a 401 (AuthFlow counts it as a wrong try).
            Failed(await Post(operation, Request(pin: "9998")));
        }
    }

    [Fact]
    public async Task AnIncompleteRequestIsInvalid()
    {
        await SeedTrustedPhone();
        Failed(await Post("sign-in", Request(pin: "5826", deviceId: "")), HttpStatusCode.BadRequest, "invalid_request");
    }

    [Fact]
    public async Task APausedAccountShowsTheTimerOnItsTrustedPhone()
    {
        await SeedTrustedPhone();
        for (var i = 0; i < 5; i++) Failed(await Post("sign-in", Request(pin: "9998")));
        foreach (var operation in new[] { "sign-in", "unlock" })
        {
            var paused = await Post(operation, Request(pin: "5826"));
            Failed(paused, (HttpStatusCode)423, "paused");
            // AuthFlow: error.response.retryAfterSeconds ?? PAUSE_SECONDS.
            Assert.True(Phase1.Has(paused.Body, "retryAfterSeconds", J.Num).GetInt32() > 0);
        }
    }

    [Fact]
    public async Task ANewPhoneVerifiesWithAnEmailCode()
    {
        await SeedTrustedPhone();
        var newPhone = Guid.NewGuid().ToString();
        var challenge = await Post("sign-in", Request(pin: "5826", deviceId: newPhone));
        Assert.True(challenge.Status == HttpStatusCode.Accepted, $"Expected 202, got {(int)challenge.Status}: {challenge.Body}");
        AuthBody(challenge.Body, "verification_required");
        // showCode: result.maskedEmail || "" and result.developmentCode || "".
        Assert.Contains("@example.com", Phase1.Has(challenge.Body, "maskedEmail", J.Str).GetString());
        Phase1.Has(challenge.Body, "developmentCode", J.Null, J.Str);

        Failed(await Post("verify-device", Request(code: "000000", deviceId: newPhone)));
        Authenticated(await Post("verify-device", Request(code: app.Email.Codes[Address], deviceId: newPhone)));
    }

    [Fact]
    public async Task AFirstPinIsSetWithAnEmailCode()
    {
        await app.Seed(withPin: false, trusted: false);
        var requested = await Post("setup-pin/request", Request());
        Assert.Equal(HttpStatusCode.Accepted, requested.Status);
        AuthBody(requested.Body, "check_email");
        var code = app.Email.Codes[Address];

        Failed(await Post("setup-pin/verify", Request(code: "000000")));
        var verified = await Post("setup-pin/verify", Request(code: code));
        Assert.Equal(HttpStatusCode.OK, verified.Status);
        AuthBody(verified.Body, "code_verified");

        // A PIN the rules refuse, then one below the organization's minimum: AuthFlow reads minimumPinLength.
        var weak = await Post("setup-pin/complete", Request(pin: "1111", code: code));
        Failed(weak, HttpStatusCode.BadRequest, "invalid_pin");
        Assert.Equal(4, Phase1.Has(weak.Body, "minimumPinLength", J.Num).GetInt32());
        await app.Policy(policy => policy.PinLength = 6);
        var short_ = await Post("setup-pin/complete", Request(pin: "5826", code: code));
        Failed(short_, HttpStatusCode.BadRequest, "invalid_pin");
        Assert.Equal(6, Phase1.Has(short_.Body, "minimumPinLength", J.Num).GetInt32());

        Failed(await Post("setup-pin/complete", Request(pin: "582694", code: "000000")));
        Authenticated(await Post("setup-pin/complete", Request(pin: "582694", code: code)));
    }

    [Fact]
    public async Task AForgottenPinIsResetWithAnEmailCode()
    {
        await SeedTrustedPhone();
        var requested = await Post("pin-reset/request", Request());
        Assert.Equal(HttpStatusCode.Accepted, requested.Status);
        AuthBody(requested.Body, "check_email");
        var code = app.Email.Codes[Address];

        Failed(await Post("pin-reset/verify", Request(code: "000000")));
        var verified = await Post("pin-reset/verify", Request(code: code));
        Assert.Equal(HttpStatusCode.OK, verified.Status);
        AuthBody(verified.Body, "code_verified");

        Failed(await Post("pin-reset/complete", Request(pin: "6942", code: "000000")));
        Authenticated(await Post("pin-reset/complete", Request(pin: "6942", code: code)));
    }

    [Fact]
    public async Task RefreshRotatesAndSignOutEndsTheSession()
    {
        await SeedTrustedPhone();
        var (_, first) = Authenticated(await Post("sign-in", Request(pin: "5826")));
        var (_, second) = Authenticated(await Post("refresh", Request(refreshToken: first)));
        Assert.NotEqual(first, second);
        // A rotated token no longer renews (renew() then ends the session).
        Failed(await Post("refresh", Request(refreshToken: first)));

        var (_, third) = Authenticated(await Post("sign-in", Request(pin: "5826")));
        var signedOut = await Post("sign-out", Request(refreshToken: third));
        Assert.Equal(HttpStatusCode.OK, signedOut.Status);
        AuthBody(signedOut.Body, "signed_out");
        Failed(await Post("refresh", Request(refreshToken: third)));
    }

    [Fact]
    public async Task SwitchUserRevokesThisPhone()
    {
        await SeedTrustedPhone();
        var (access, refresh) = Authenticated(await Post("sign-in", Request(pin: "5826")));
        // forgetThisPhone: devices/{its own id}/revoke with its access token. Without one it is a 401, which the
        // phone answers by renewing and trying again.
        var anonymous = await Post($"devices/{Uri.EscapeDataString(device)}/revoke", Request(refreshToken: refresh));
        Assert.Equal(HttpStatusCode.Unauthorized, anonymous.Status);

        var revoked = await Post($"devices/{Uri.EscapeDataString(device)}/revoke", Request(refreshToken: refresh), access);
        Assert.True(revoked.Status == HttpStatusCode.OK, $"Expected 200 device_revoked, got {(int)revoked.Status}: {revoked.Body}");
        AuthBody(revoked.Body, "device_revoked");
        Assert.Equal(HttpStatusCode.Unauthorized, (await Get("/auth/session", access)).Status);
        Failed(await Post("refresh", Request(refreshToken: refresh)));
    }

    [Fact]
    public async Task TheSessionNamesThePersonAndTheirPermissions()
    {
        await SeedTrustedPhone();
        var (access, _) = Authenticated(await Post("sign-in", Request(pin: "5826")));
        var (status, session) = await Get("/auth/session", access);
        Assert.Equal(HttpStatusCode.OK, status);
        // apps/mobile/src/session.ts AuthSession and apps/web/lib/session-context.tsx Session.
        Assert.True(Guid.TryParse(Phase1.Has(session, "userId", J.Str).GetString(), out _));
        Phase1.Has(session, "firstName", J.Str);
        Phase1.Has(session, "lastName", J.Str);
        Assert.Equal("Revenue clerk", Phase1.Has(session, "role", J.Str).GetString());
        Phase1.Strings(session, "permissions");
        Assert.NotEmpty(session.GetProperty("permissions").EnumerateArray());

        // apiGet renews on a 401 and ends the session on a second one, so a missing or bad token must stay a 401.
        Assert.Equal(HttpStatusCode.Unauthorized, (await Get("/auth/session", null)).Status);
        Assert.Equal(HttpStatusCode.Unauthorized, (await Get("/auth/session", "not-a-token")).Status);
    }

    public void Dispose()
    {
        client.Dispose();
        app.Dispose();
    }
}

// Read by both Phase 1 clients: the phone's theme and "Your access", and the web shell.
public sealed class Phase1AppearanceAndCatalogContractTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";

    [Fact]
    public async Task AppearanceKeepsEveryFieldTheClientsRead()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn(RevenueClerk);
        using var response = await clerk.GetAsync("/setup/appearance");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var appearance = await Phase1.Body(response);

        // apps/mobile/src/appearance.ts Appearance and apps/web/lib/appearance.ts Appearance.
        Phase1.Has(appearance, "organizationName", J.Str);
        Phase1.Has(appearance, "settingsVersion", J.Num);
        var branding = Phase1.Has(appearance, "branding", J.Obj);
        foreach (var name in new[] { "displayName", "logoAlt", "primary", "secondary", "accent" })
            Phase1.Has(branding, name, J.Str);
        Phase1.Has(branding, "logo", J.Str, J.Null);
        // apps/mobile/src/lib/format.ts Formats (useGroupping is spelled so), plus the web's extra three.
        var formats = Phase1.Has(appearance, "formats", J.Obj);
        foreach (var name in new[] { "locale", "timeZone", "datePattern", "currency", "weekNumbering", "direction" })
            Phase1.Has(formats, name, J.Str);
        Phase1.Has(formats, "hour12", J.Bool);
        Phase1.Has(formats, "useGroupping", J.Bool);
        Phase1.Has(formats, "numberDecimals", J.Num);
        Phase1.Has(formats, "firstDayOfWeek", J.Num);
        Phase1.Has(appearance, "themeMode", J.Str);
        Phase1.Has(appearance, "reducedMotion", J.Bool);
        Phase1.Has(appearance, "fontScale", J.Num);

        using var anonymous = app.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await anonymous.GetAsync("/setup/appearance")).StatusCode);
    }

    [Fact]
    public async Task TheCatalogKeepsItsShapeAndTheNamesThePhoneLooksFor()
    {
        await app.SeedDemo();
        using var clerk = await app.SignIn(RevenueClerk);
        using var response = await clerk.GetAsync("/setup/access/catalog");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var catalog = await Phase1.Body(response);

        // PermissionGroup[] as apps/mobile/src/shell/access.ts and apps/web/lib/types.ts read it.
        Assert.Equal(JsonValueKind.Array, catalog.ValueKind);
        var groups = catalog.EnumerateArray().ToArray();
        Assert.NotEmpty(groups);
        var keys = new HashSet<string>();
        foreach (var group in groups)
        {
            Phase1.Has(group, "name", J.Str);
            foreach (var item in Phase1.Items(group, "items"))
            {
                keys.Add(Phase1.Has(item, "key", J.Str).GetString()!);
                Phase1.Has(item, "label", J.Str);
                Phase1.Strings(item, "needs");
            }
        }

        // The phone's Revenue and Spend tabs list the labels of these groups by name.
        var names = groups.Select(group => group.GetProperty("name").GetString()).ToHashSet();
        Assert.Subset(names, new HashSet<string?> { "Revenue", "Petty cash", "Office bills" });
        // Permission keys the phone's tabs, dashboard cards and setup links test for.
        Assert.Subset(keys, new HashSet<string>
        {
            "revenue.view", "revenue.capture", "pettycash.spend", "pettycash.approve_item", "pettycash.view_all", "bills.view",
            "dash.capture", "dash.revenue", "dash.net", "dash.costs", "dash.gaps", "dash.commitments", "dash.edits",
            "companies.manage", "vehicles.manage", "commitments.view", "people.view", "audit.view", "organization.manage"
        });

        using var anonymous = app.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await anonymous.GetAsync("/setup/access/catalog")).StatusCode);
    }

    public void Dispose() => app.Dispose();
}

// The develop web app calls much more of /setup than the phone does (its proxy allows companies, vehicles, recurring,
// history, preferences, appearance, organization/logo, organization/settings, access/* and people). A browser tab
// still running the develop bundle sends exactly these requests.
public sealed class Phase1WebSettingsContractTests : IDisposable
{
    private readonly AuthFactory app = new();
    private const string Owner = "antony.maina@shamayah.co.ke";
    private const string RevenueClerk = "wanjiru.kamau@zurigenesis.co.ke";
    private const string Png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

    private DateOnly Today => DateOnly.FromDateTime(app.Clock.UtcNow.UtcDateTime);

    // The develop proxy forwards the browser's JSON unchanged. A POST without one (people/{id}/activate and the like)
    // goes upstream as fetch(..., { body: "" }), which fetch sends as an empty text/plain body.
    private static async Task<(HttpStatusCode Status, JsonElement Body)> Send(HttpClient client, HttpMethod method, string path, object? body = null)
    {
        using var request = new HttpRequestMessage(method, "/setup/" + path);
        if (body is not null) request.Content = Phase1.Json(body);
        else if (method != HttpMethod.Get && method != HttpMethod.Delete) request.Content = new StringContent("", Encoding.UTF8, "text/plain");
        using var response = await client.SendAsync(request);
        return (response.StatusCode, await Phase1.Body(response));
    }

    private static JsonElement Ok((HttpStatusCode Status, JsonElement Body) result, string what)
    {
        Assert.True(result.Status == HttpStatusCode.OK, $"{what} returned {(int)result.Status}: {result.Body}");
        return result.Body;
    }

    private static string Created((HttpStatusCode Status, JsonElement Body) result, string what) =>
        Phase1.Has(Ok(result, what), "id", J.Str).GetString()!;

    // The develop web's CompaniesPage and VehiclesPage bodies.
    private async Task<(string Company, string Vehicle)> AddFleet(HttpClient owner)
    {
        var company = Created(await Send(owner, HttpMethod.Post, "companies", new { name = "Contract Fleet", reason = "Added PSV company Contract Fleet" }), "POST companies");
        var vehicle = Created(await Send(owner, HttpMethod.Post, "vehicles", new
        {
            registration = "KDA 123A", companyId = company, weeklyTarget = 21000, joinedOn = Phase1.Date(Today), reason = "Added vehicle KDA 123A"
        }), "POST vehicles");
        return (company, vehicle);
    }

    // RecurringEditor.save as develop sends it.
    private object Recurring(string vehicle, string name, int kind, int? category, int frequency, int? day, decimal amount, string reason) => new
    {
        name, kind, category, amount, frequency, day, lastDay = false, start = Phase1.Date(Today), end = (string?)null,
        allocations = new[] { new { vehicleId = vehicle, amount } }, reason
    };

    // PeopleAccessView's save body for a new revenue clerk who sees one vehicle.
    private static object Person(string vehicle, IEnumerable<string> permissions) => new
    {
        firstName = "Grace", lastName = "Njeri", email = "grace.njeri@example.com", phoneNumber = "0712000111", role = "Revenue clerk",
        scopeMode = "vehicles", companyIds = Array.Empty<string>(), vehicleIds = new[] { vehicle }, permissions, approvalLimit = (decimal?)null
    };

    private static async Task<string[]> ClerkDefaults(HttpClient owner) =>
        Ok(await Send(owner, HttpMethod.Get, "access/roles"), "GET access/roles").EnumerateArray()
            .Single(role => role.GetProperty("name").GetString() == "Revenue clerk")
            .GetProperty("permissions").EnumerateArray().Select(x => x.GetString()!).ToArray();

    [Fact]
    public async Task FleetScreensReadAndWriteAsTheDevelopWebDoes()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (company, vehicle) = await AddFleet(owner);
        Ok(await Send(owner, HttpMethod.Put, $"companies/{company}", new { name = "Contract Fleet Ltd", reason = "Renamed Contract Fleet to Contract Fleet Ltd" }), "PUT companies/{id}");
        Ok(await Send(owner, HttpMethod.Put, $"vehicles/{vehicle}", new
        {
            registration = "KDA 123A", companyId = company, weeklyTarget = 24500, joinedOn = Phase1.Date(Today), reason = "Updated vehicle KDA 123A"
        }), "PUT vehicles/{id}");

        // apps/web/components/setup/shared.tsx Company.
        var companies = Phase1.Page(Ok(await Send(owner, HttpMethod.Get, "companies?page=1&pageSize=25"), "GET companies"));
        Assert.NotEmpty(companies);
        foreach (var item in companies)
        {
            Phase1.Has(item, "id", J.Str);
            Phase1.Has(item, "name", J.Str);
            Phase1.Has(item, "vehicleCount", J.Num);
        }

        // Vehicle.
        var vehicles = Phase1.Page(Ok(await Send(owner, HttpMethod.Get, "vehicles?page=1&pageSize=25"), "GET vehicles"));
        Assert.NotEmpty(vehicles);
        foreach (var item in vehicles)
        {
            foreach (var name in new[] { "id", "companyId", "companyName", "registration", "joinedOn" })
                Phase1.Has(item, name, J.Str);
            Phase1.Has(item, "weeklyTarget", J.Num);
            Phase1.Has(item, "recurringItems", J.Num);
            foreach (var target in Phase1.Items(item, "targets"))
            {
                Phase1.Has(target, "effectiveFrom", J.Str);
                Phase1.Has(target, "weeklyAmount", J.Num);
                Phase1.Has(target, "revision", J.Num);
            }
        }

        // A saving posting today, so the lists and the vehicle report have a row to read.
        var saving = Created(await Send(owner, HttpMethod.Post, "recurring",
            Recurring(vehicle, "Fuel reserve", kind: 2, category: null, frequency: 2, day: (int)Today.DayOfWeek, 1400, "Added recurring item Fuel reserve")), "POST recurring (saving)");

        // VehicleOption.
        var options = Ok(await Send(owner, HttpMethod.Get, "recurring/vehicle-options"), "GET recurring/vehicle-options");
        Assert.NotEmpty(options.EnumerateArray());
        foreach (var item in options.EnumerateArray())
            foreach (var name in new[] { "id", "companyId", "companyName", "registration" })
                Phase1.Has(item, name, J.Str);

        // RecurringItem.
        var recurring = Phase1.Page(Ok(await Send(owner, HttpMethod.Get, "recurring?page=1&pageSize=25"), "GET recurring"));
        Assert.NotEmpty(recurring);
        foreach (var item in recurring)
        {
            foreach (var name in new[] { "id", "name", "start" })
                Phase1.Has(item, name, J.Str);
            foreach (var name in new[] { "kind", "amount", "frequency" })
                Phase1.Has(item, name, J.Num);
            Phase1.Has(item, "category", J.Num, J.Null);
            Phase1.Has(item, "day", J.Num, J.Null);
            Phase1.Has(item, "lastDay", J.Bool);
            Phase1.Has(item, "end", J.Str, J.Null);
            Phase1.Has(item, "stoppedFrom", J.Str, J.Null);
            Phase1.Has(item, "partial", J.Bool);
            foreach (var share in Phase1.Items(item, "allocations"))
            {
                Phase1.Has(share, "vehicleId", J.Str);
                Phase1.Has(share, "amount", J.Num);
                Phase1.Has(share, "registration", J.Str, J.Null);
            }
        }

        // VehicleReport and Posting, for both periods the develop page offers.
        foreach (var period in new[] { "month", "week" })
        {
            var report = Ok(await Send(owner, HttpMethod.Get, $"vehicles/{vehicle}/report?period={period}"), $"GET vehicles/{{id}}/report?period={period}");
            foreach (var name in new[] { "vehicleId", "from", "through" })
                Phase1.Has(report, name, J.Str);
            Phase1.Has(report, "costs", J.Num);
            Phase1.Has(report, "savings", J.Num);
            var postings = Phase1.Items(report, "postings");
            Assert.NotEmpty(postings);
            foreach (var posting in postings)
            {
                foreach (var name in new[] { "itemId", "versionId", "date", "name" })
                    Phase1.Has(posting, name, J.Str);
                Phase1.Has(posting, "kind", J.Num);
                Phase1.Has(posting, "category", J.Num, J.Null);
                Phase1.Has(posting, "amount", J.Num);
            }
        }

        Ok(await Send(owner, HttpMethod.Put, $"recurring/{saving}",
            Recurring(vehicle, "Fuel reserve", kind: 2, category: null, frequency: 2, day: (int)Today.DayOfWeek, 1500, "Updated recurring item Fuel reserve")), "PUT recurring/{id}");
        Ok(await Send(owner, HttpMethod.Post, $"recurring/{saving}/stop", new { confirmed = true, reason = "Stopped recurring item" }), "POST recurring/{id}/stop");

        // HistoryRow, from the change-log page (streamed) and the people page's latest three.
        foreach (var path in new[] { "history?page=1&pageSize=25", "history?pageSize=3" })
        {
            var history = Phase1.Page(Ok(await Send(owner, HttpMethod.Get, path), "GET " + path));
            Assert.NotEmpty(history);
            foreach (var entry in history)
            {
                Phase1.Has(entry, "version", J.Num);
                foreach (var name in new[] { "section", "entityId", "reason", "occurredAt", "actorId", "actorName" })
                    Phase1.Has(entry, name, J.Str);
            }
        }
    }

    // Addendum 1 changed these rules on purpose: a cost now picks an expense item, and daily schedules are gone. A stale
    // Phase 1 web tab is refused with a problem it can show (so the person reloads), never a 415 or 500.
    [Fact]
    public async Task ARecurringCostFromTheDevelopWebIsRefusedWithAReason()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicle) = await AddFleet(owner);
        var refused = await Send(owner, HttpMethod.Post, "recurring",
            Recurring(vehicle, "Stage fees", kind: 1, category: 1, frequency: 2, day: (int)Today.DayOfWeek, 300, "Added recurring item Stage fees"));
        Assert.Equal(HttpStatusCode.BadRequest, refused.Status);
        Phase1.Problem(refused.Body);
    }

    [Fact]
    public async Task ADailyItemFromTheDevelopWebIsRefusedWithAReason()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicle) = await AddFleet(owner);
        var refused = await Send(owner, HttpMethod.Post, "recurring",
            Recurring(vehicle, "Daily reserve", kind: 2, category: null, frequency: 1, day: null, 200, "Added recurring item Daily reserve"));
        Assert.Equal(HttpStatusCode.BadRequest, refused.Status);
        Phase1.Problem(refused.Body);
    }

    [Fact]
    public async Task PeopleAndAccessReadAsTheDevelopWebDoes()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicle) = await AddFleet(owner);

        // Role.
        var roles = Ok(await Send(owner, HttpMethod.Get, "access/roles"), "GET access/roles");
        Assert.NotEmpty(roles.EnumerateArray());
        foreach (var role in roles.EnumerateArray())
        {
            Phase1.Has(role, "id", J.Str);
            Phase1.Has(role, "name", J.Str);
            Phase1.Strings(role, "permissions");
        }

        // ScopeOptions.
        var scope = Ok(await Send(owner, HttpMethod.Get, "access/scope-options"), "GET access/scope-options");
        foreach (var item in Phase1.Items(scope, "companies"))
        {
            Phase1.Has(item, "id", J.Str);
            Phase1.Has(item, "name", J.Str);
        }
        var scopeVehicles = Phase1.Items(scope, "vehicles");
        Assert.NotEmpty(scopeVehicles);
        foreach (var item in scopeVehicles)
            foreach (var name in new[] { "id", "registration", "companyId" })
                Phase1.Has(item, name, J.Str);

        var person = Created(await Send(owner, HttpMethod.Post, "people", Person(vehicle, await ClerkDefaults(owner))), "POST people");

        // Person (apps/web/lib/types.ts).
        var people = Phase1.Page(Ok(await Send(owner, HttpMethod.Get, "people?page=1&pageSize=25"), "GET people"));
        Assert.Contains(people, item => item.GetProperty("id").GetString() == person);
        foreach (var item in people)
        {
            foreach (var name in new[] { "id", "firstName", "lastName", "email", "phoneNumber", "role", "scopeMode" })
                Phase1.Has(item, name, J.Str);
            Phase1.Has(item, "active", J.Bool);
            Phase1.Has(item, "hasPin", J.Bool);
            Phase1.Strings(item, "companyIds");
            Phase1.Strings(item, "vehicleIds");
            Phase1.Strings(item, "permissions");
            Phase1.Has(item, "approvalLimit", J.Num, J.Null);
        }

        // Signing a person out takes no body and still works.
        Ok(await Send(owner, HttpMethod.Post, $"people/{person}/sign-out"), "POST people/{id}/sign-out");
    }

    // People edits now carry the version they were loaded at, so two editors cannot silently overwrite each other. The
    // develop web sends none: it is asked to reload, with a problem it can show.
    [Fact]
    public async Task EditingAPersonFromTheDevelopWebAsksForAReload()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicle) = await AddFleet(owner);
        var permissions = await ClerkDefaults(owner);
        var person = Created(await Send(owner, HttpMethod.Post, "people", Person(vehicle, permissions)), "POST people");
        var refused = await Send(owner, HttpMethod.Put, $"people/{person}", Person(vehicle, permissions));
        Assert.Equal(HttpStatusCode.BadRequest, refused.Status);
        Phase1.Problem(refused.Body);
    }

    // PeopleAccessView.lifecycle posts activate and deactivate with no body. Removing access now needs a typed reason and
    // both need the loaded version; the body-less call gets a problem the web can show, never a 415.
    [Fact]
    public async Task RemovingAccessFromTheDevelopWebAsksForAReload()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        var (_, vehicle) = await AddFleet(owner);
        var person = Created(await Send(owner, HttpMethod.Post, "people", Person(vehicle, await ClerkDefaults(owner))), "POST people");
        foreach (var action in new[] { "deactivate", "activate" })
        {
            var refused = await Send(owner, HttpMethod.Post, $"people/{person}/{action}");
            Assert.True((int)refused.Status is >= 400 and < 500 && refused.Status != HttpStatusCode.UnsupportedMediaType,
                $"POST people/{{id}}/{action} with no body gave {(int)refused.Status}: {refused.Body}");
            if (refused.Status != HttpStatusCode.OK) Phase1.Problem(refused.Body);
        }
    }

    [Fact]
    public async Task OrganizationSettingsAndPreferencesReadAndSaveAsTheDevelopWebDoes()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);

        // OrganizationSettingsView Settings.
        var settings = Ok(await Send(owner, HttpMethod.Get, "organization/settings"), "GET organization/settings");
        var organization = Phase1.Has(settings, "organization", J.Obj);
        Phase1.Has(organization, "name", J.Str);
        Phase1.Has(organization, "slug", J.Str);
        var localization = Phase1.Has(settings, "localization", J.Obj);
        foreach (var name in new[] { "locale", "timeZone", "currency", "datePattern", "weekNumbering" })
            Phase1.Has(localization, name, J.Str);
        foreach (var name in new[] { "hour12", "useGroupping", "allowLocaleOverride", "allowTimeZoneOverride", "allowHour12Override", "allowThemeOverride" })
            Phase1.Has(localization, name, J.Bool);
        Phase1.Has(localization, "firstDayOfWeek", J.Num);
        Phase1.Has(localization, "numberDecimals", J.Num);
        var branding = Phase1.Has(settings, "branding", J.Obj);
        foreach (var name in new[] { "displayName", "legalName", "logoAlt", "primary", "secondary", "accent" })
            Phase1.Has(branding, name, J.Str);
        Phase1.Has(branding, "supportEmail", J.Str, J.Null);
        Phase1.Has(branding, "domain", J.Str, J.Null);
        var policy = Phase1.Has(settings, "securityPolicy", J.Obj);
        foreach (var name in new[] { "passwordMinLength", "passwordHistory", "pinLength", "lockoutThreshold", "lockoutMinutes", "accessTokenMinutes", "refreshTokenDays", "idleUnlockSeconds" })
            Phase1.Has(policy, name, J.Num);
        Phase1.Has(policy, "passwordComplexity", J.Bool);
        Phase1.Has(policy, "allowPinSignIn", J.Bool);

        // save(section): { value: the section as loaded and edited, reason }.
        Ok(await Send(owner, HttpMethod.Put, "organization/settings/organization",
            new { value = new { name = "Demo Fleet Ltd", slug = "demo-fleet" }, reason = "Updated organization details" }), "PUT organization/settings/organization");
        Ok(await Send(owner, HttpMethod.Put, "organization/settings/localization", new { value = localization, reason = "Updated locale and time" }), "PUT organization/settings/localization");
        Ok(await Send(owner, HttpMethod.Put, "organization/settings/branding", new { value = branding, reason = "Updated brand" }), "PUT organization/settings/branding");
        Ok(await Send(owner, HttpMethod.Put, "organization/settings/securityPolicy", new { value = policy, reason = "Updated security policy" }), "PUT organization/settings/securityPolicy");
        // changeLogo.
        Ok(await Send(owner, HttpMethod.Put, "organization/logo", new { dataUrl = Png }), "PUT organization/logo");
        Ok(await Send(owner, HttpMethod.Delete, "organization/logo"), "DELETE organization/logo");

        // PreferencesView Preferences, saved back as loaded.
        var preferences = Ok(await Send(owner, HttpMethod.Get, "preferences"), "GET preferences");
        Phase1.Has(preferences, "locale", J.Str, J.Null);
        Phase1.Has(preferences, "timeZone", J.Str, J.Null);
        Phase1.Has(preferences, "hour12", J.Bool, J.Null);
        Phase1.Has(preferences, "themeMode", J.Str, J.Null);
        Phase1.Has(preferences, "reducedMotion", J.Bool);
        Phase1.Has(preferences, "fontScale", J.Num);
        foreach (var name in new[] { "allowLocaleOverride", "allowTimeZoneOverride", "allowHour12Override", "allowThemeOverride" })
            Phase1.Has(preferences, name, J.Bool);
        var defaults = Phase1.Has(preferences, "organization", J.Obj);
        Phase1.Has(defaults, "locale", J.Str);
        Phase1.Has(defaults, "timeZone", J.Str);
        Phase1.Has(defaults, "hour12", J.Bool);
        Ok(await Send(owner, HttpMethod.Put, "preferences", preferences), "PUT preferences");
    }

    [Fact]
    public async Task RefusalsKeepTheirStatusAndAProblemTheWebCanShow()
    {
        await app.SeedDemo();
        using var owner = await app.SignIn(Owner);
        using var clerk = await app.SignIn(RevenueClerk);

        var invalid = await Send(owner, HttpMethod.Post, "companies", new { name = "", reason = "Added PSV company " });
        Assert.Equal(HttpStatusCode.BadRequest, invalid.Status);
        Phase1.Problem(invalid.Body);

        var forbidden = await Send(clerk, HttpMethod.Get, "organization/settings");
        Assert.Equal(HttpStatusCode.Forbidden, forbidden.Status);
        Phase1.Problem(forbidden.Body);

        var missing = await Send(owner, HttpMethod.Get, $"vehicles/{Guid.NewGuid()}/report?period=month");
        Assert.Equal(HttpStatusCode.NotFound, missing.Status);
        Phase1.Problem(missing.Body);

        // useResource and useStreamedList refresh once on a 401, so it must stay a 401.
        using var anonymous = app.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await anonymous.GetAsync("/setup/companies?page=1&pageSize=25")).StatusCode);
    }

    public void Dispose() => app.Dispose();
}
