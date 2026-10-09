using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed partial class AuthDb
{
    private void ConfigureCentralExpenses(ModelBuilder model)
    {
        var expense = model.Entity<CentralExpense>();
        expense.HasKey(x => new { x.OrganizationId, x.Id });
        Tenant(expense);
        expense.Ignore(x => x.Removed);
        expense.Property(x => x.Units).HasPrecision(12, 3);
        expense.Property(x => x.UnitAmount).HasPrecision(14, 2);
        expense.Property(x => x.Total).HasPrecision(14, 2);
        expense.Property(x => x.GroupTotal).HasPrecision(14, 2);
        expense.Property(x => x.GroupUnits).HasPrecision(12, 3);
        expense.Property(x => x.GroupUnitAmount).HasPrecision(14, 2);
        expense.Property(x => x.Note).HasMaxLength(CentralExpense.NoteLength);
        expense.Property(x => x.RemovalReason).HasMaxLength(CentralExpense.ReasonLength);
        expense.Property(x => x.Version).IsConcurrencyToken();
        expense.HasIndex(x => new { x.OrganizationId, x.Date });
        expense.HasIndex(x => new { x.OrganizationId, x.VehicleId, x.Date });
        expense.HasIndex(x => new { x.OrganizationId, x.GroupId, x.VehicleId }).IsUnique();
        expense.HasOne<FleetVehicle>().WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.VehicleId })
            .OnDelete(DeleteBehavior.Restrict);
        expense.HasOne<ExpenseItem>().WithMany()
            .HasForeignKey(x => new { x.OrganizationId, x.ExpenseItemId })
            .OnDelete(DeleteBehavior.Restrict);
    }
}
