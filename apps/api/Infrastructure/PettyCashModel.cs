using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed partial class AuthDb
{
    private void ConfigurePettyCash(ModelBuilder model)
    {
        var entry = model.Entity<PettyCashEntry>();
        entry.HasKey(x => new { x.OrganizationId, x.Id });
        Tenant(entry);
        entry.Ignore(x => x.Removed);
        entry.Ignore(x => x.Reviewed);
        entry.Ignore(x => x.Effect);
        entry.Property(x => x.Units).HasPrecision(12, 3);
        entry.Property(x => x.UnitAmount).HasPrecision(14, 2);
        entry.Property(x => x.Total).HasPrecision(14, 2);
        entry.Property(x => x.Payee).HasMaxLength(PettyCashLine.PayeeLength);
        entry.Property(x => x.Note).HasMaxLength(PettyCashLine.NoteLength);
        entry.Property(x => x.SentBackNote).HasMaxLength(PettyCashLine.CommentLength);
        entry.Property(x => x.RemovalReason).HasMaxLength(500);
        entry.Property(x => x.Version).IsConcurrencyToken();
        entry.HasIndex(x => new { x.OrganizationId, x.HolderId, x.Date });
        entry.HasIndex(x => new { x.OrganizationId, x.Status, x.Date });
        entry.HasIndex(x => new { x.OrganizationId, x.VehicleId, x.Date });
        entry.HasOne<OrganizationMembership>().WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.HolderId })
            .OnDelete(DeleteBehavior.Restrict);
        entry.HasOne<FleetVehicle>().WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.VehicleId })
            .OnDelete(DeleteBehavior.Restrict);
        entry.HasOne<ExpenseItem>().WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.ExpenseItemId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}
