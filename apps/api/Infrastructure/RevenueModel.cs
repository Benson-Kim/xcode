using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed partial class AuthDb
{
    private void ConfigureRevenue(ModelBuilder model)
    {
        var record = model.Entity<RevenueRecord>();
        record.HasKey(x => new { x.OrganizationId, x.Id });
        Tenant(record);
        record.Property(x => x.Amount).HasPrecision(14, 2);
        record.Property(x => x.Note).HasMaxLength(80);
        record.Property(x => x.Version).IsConcurrencyToken();
        record.HasIndex(x => new { x.OrganizationId, x.VehicleId, x.BusinessDate }).IsUnique();
        record.HasIndex(x => new { x.OrganizationId, x.BusinessDate });
        record.HasOne<FleetVehicle>().WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.VehicleId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}
