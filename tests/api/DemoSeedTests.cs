using System.Net;
using System.Net.Http.Json;
using Auth.Application;
using Auth.Infrastructure;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace Auth.Tests;

public sealed class DemoSeedTests : IDisposable
{
    private readonly AuthFactory app = new();

    [Fact]
    public async Task DesignLoginsSignInWithTheirPins_AndReseedingKeepsChangedPins()
    {
        await app.WithDb(async db => { await db.Database.EnsureCreatedAsync(); await AuthFactory.AddOrganization(db); await DemoSeed.Run(db); });
        using var client = app.CreateClient();
        foreach (var (phoneNumber, email, pin) in DemoSeed.Logins.Where(l => l.Pin is not null))
        {
            // A correct PIN on an untrusted phone asks for an email code; a wrong one is a 401.
            var response = await client.PostAsJsonAsync("/auth/sign-in", new AuthRequest(PhoneNumber: phoneNumber, Pin: pin!, DeviceId: "new-phone"));
            Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        }
        await app.WithDb(async db =>
        {
            Assert.Null((await db.Users.SingleAsync(u => u.Email == "brian.mwangi@metrotrans.co.ke")).PinHash);
            var owner = await db.Users.SingleAsync(u => u.Email == "antony.maina@shamayah.co.ke");
            owner.PinHash = PinHasher.Hash("9731");
            await db.SaveChangesAsync();
            await DemoSeed.Run(db);
            Assert.Equal(DemoSeed.Logins.Length, await db.Users.CountAsync());
            Assert.True(PinHasher.Verify("9731", (await db.Users.AsNoTracking().SingleAsync(u => u.Id == owner.Id)).PinHash!));
        });
    }

    public void Dispose() => app.Dispose();
}
