using Auth.Domain;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

// Development only: the demo logins from design/XCODE_Web.html and design/XCODE_Mobile.html.
public static class DemoSeed
{
    public static readonly (string PhoneNumber, string Email, string? Pin)[] Logins =
    [
        ("+254733520614", "antony.maina@shamayah.co.ke", "4826"),     // Owner
        ("+254722410355", "peter.otieno@zurigenesis.co.ke", "1379"),  // Office admin
        ("+254700111222", "brian.mwangi@metrotrans.co.ke", null),     // Fleet manager: sets a PIN with an email code
        ("+254712345678", "wanjiru.kamau@zurigenesis.co.ke", "2580"), // Revenue clerk
    ];


    // Adds missing people only, so a PIN changed or reset during development survives restarts.
    public static async Task Run(AuthDb db, CancellationToken cancellationToken = default)
    {
        var existing = await db.Users.Select(u => u.Email).ToListAsync(cancellationToken);
        foreach (var (phonenumber, email, pin) in Logins.Where(l => !existing.Contains(l.Email)))
            db.Users.Add(new User { PhoneNumber = phonenumber, Email = email, PinHash = pin is null ? null : PinHasher.Hash(pin) });
        await db.SaveChangesAsync(cancellationToken);
    }
}
