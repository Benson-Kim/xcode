
using Auth.Domain;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure;

public sealed partial class AuthDb
{
     private void ConfigureSetup(ModelBuilder model)

     {
          var company = model.Entity<PsvCompany>();
          company.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(company);
          company.Property(x => x.Name).HasMaxLength(160);
          company.Property(x => x.NormalizedName).HasMaxLength(160);
          company.HasIndex(x => new { x.OrganizationId, x.NormalizedName }).IsUnique();

          var vehicle = model.Entity<FleetVehicle>();
          vehicle.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(vehicle);
          vehicle.Property(x => x.Registration).HasMaxLength(8);
          vehicle.HasIndex(x => new { x.OrganizationId, x.Registration }).IsUnique();
          vehicle.HasOne<PsvCompany>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.CompanyId }).OnDelete(DeleteBehavior.Restrict);

          var target = model.Entity<VehicleTarget>();
          target.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(target);
          target.Property(x => x.WeeklyAmount).HasPrecision(14, 2);
          target.HasIndex(x => new { x.OrganizationId, x.VehicleId, x.Revision }).IsUnique();
          target.HasOne<FleetVehicle>().WithMany(x => x.Targets).HasForeignKey(x => new { x.OrganizationId, x.VehicleId }).OnDelete(DeleteBehavior.Restrict);

          var item = model.Entity<RecurringItem>();
          item.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(item);

          var version = model.Entity<RecurringVersion>();
          version.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(version);
          version.Property(x => x.Name).HasMaxLength(160);
          version.Property(x => x.Amount).HasPrecision(14, 2);
          version.HasIndex(x => new { x.OrganizationId, x.ItemId, x.Revision }).IsUnique();
          version.HasOne<RecurringItem>().WithMany(x => x.Versions).HasForeignKey(x => new { x.OrganizationId, x.ItemId }).OnDelete(DeleteBehavior.Restrict);

          var allocation = model.Entity<RecurringAllocation>();
          allocation.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(allocation);
          allocation.Property(x => x.Amount).HasPrecision(14, 2);
          allocation.HasIndex(x => new { x.OrganizationId, x.VersionId, x.VehicleId }).IsUnique();
          allocation.HasOne<RecurringVersion>().WithMany(x => x.Allocations).HasForeignKey(x => new { x.OrganizationId, x.VersionId }).OnDelete(DeleteBehavior.Restrict);
          allocation.HasOne<FleetVehicle>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.VehicleId }).OnDelete(DeleteBehavior.Restrict);

          var history = model.Entity<OrganizationSettingsVersion>();
          history.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(history);
          history.HasIndex(x => new { x.OrganizationId, x.Version }).IsUnique();
          history.Property(x => x.Section).HasMaxLength(160);
          history.Property(x => x.Reason).HasMaxLength(500);
          history.Property(x => x.CorrelationId).HasMaxLength(100);
          history.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, UserId = x.ActorId }).OnDelete(DeleteBehavior.Restrict);

          var scope = model.Entity<SetupDataScope>();
          scope.HasKey(x => new { x.OrganizationId, x.UserId }); Tenant(scope);
          scope.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);

          var companyScope = model.Entity<SetupCompanyScope>();
          companyScope.HasKey(x => new { x.OrganizationId, x.UserId, x.CompanyId }); Tenant(companyScope);
          companyScope.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);
          companyScope.HasOne<PsvCompany>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.CompanyId }).OnDelete(DeleteBehavior.Restrict);

          var vehicleScope = model.Entity<SetupVehicleScope>();
          vehicleScope.HasKey(x => new { x.OrganizationId, x.UserId, x.VehicleId }); Tenant(vehicleScope);
          vehicleScope.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);
          vehicleScope.HasOne<FleetVehicle>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.VehicleId }).OnDelete(DeleteBehavior.Restrict);

          model.Entity<RecurrenceFrequencyLookup>().HasData(Enum.GetValues<RecurrenceFrequency>().Select(x => new RecurrenceFrequencyLookup { Id = x, Name = x.ToString() }));
          model.Entity<RecurringKindLookup>().HasData(Enum.GetValues<RecurringKind>().Select(x => new RecurringKindLookup { Id = x, Name = x.ToString() }));
          model.Entity<CostCategoryLookup>().HasData(Enum.GetValues<CostCategory>().Select(x => new CostCategoryLookup { Id = x, Name = x.ToString() }));

          version.HasOne<RecurrenceFrequencyLookup>().WithMany().HasForeignKey(x => x.Frequency).OnDelete(DeleteBehavior.Restrict);
          version.HasOne<RecurringKindLookup>().WithMany().HasForeignKey(x => x.Kind).OnDelete(DeleteBehavior.Restrict);
          version.HasOne<CostCategoryLookup>().WithMany().HasForeignKey(x => x.Category).OnDelete(DeleteBehavior.Restrict);

     }

     private void ValidateSetupWrites()
     {
          foreach (var entry in ChangeTracker.Entries().Where(e => e.State is EntityState.Modified or EntityState.Deleted))
          {
               if (entry.Entity is OrganizationSettingsVersion or VehicleTarget or RecurringVersion or RecurringAllocation)
                    throw new InvalidOperationException("Setup versions and allocations are append-only.");
               if (entry.Entity is PsvCompany or FleetVehicle or RecurringItem && entry.State == EntityState.Deleted)
                    throw new InvalidOperationException("Setup records cannot be deleted.");
               if (entry.Entity is FleetVehicle && entry.Property(nameof(FleetVehicle.Registration)).IsModified)
                    throw new InvalidOperationException("Registration cannot change.");
          }
     }
}
