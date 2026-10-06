

using Auth.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Microsoft.EntityFrameworkCore.Metadata.Internal;

namespace Auth.Infrastructure;

public sealed partial class AuthDb
{
     private void Tenant<T>(EntityTypeBuilder<T> entity) where T : class, IOrganizationEntity
     {
          entity.HasOne<Organization>().WithMany().HasForeignKey(x => x.OrganizationId).OnDelete(DeleteBehavior.Restrict);
          entity.HasQueryFilter(x => x.OrganizationId == CurrentOganizationId);
     }

     private void ConfigureOrganizations(ModelBuilder model)
     {
          model.Entity<Organization>().HasIndex(x => x.Slug).IsUnique();
          model.Entity<Organization>().Property(x => x.Slug).HasMaxLength(100);
          model.Entity<Organization>().Property(x => x.Name).HasMaxLength(200);
          model.Entity<Organization>().Property(x => x.SettingsVersion).IsConcurrencyToken();
          model.Entity<Organization>().HasQueryFilter(x => x.Id == CurrentOganizationId);

          var member = model.Entity<OrganizationMembership>();
          member.HasKey(x => new { x.OrganizationId, x.UserId }); Tenant(member);
          member.Property(x => x.Version).IsConcurrencyToken();
          member.Property(x => x.ApprovalLimit).HasPrecision(14, 2);
          member.HasOne<User>().WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Restrict);
          // Sign-in and token issue expect one active membership per person; the database now guarantees it. The plain
          // UserId index stays for the foreign key, so the filtered one does not replace it.
          member.HasIndex(x => x.UserId);
          member.HasIndex(x => x.UserId, "IX_Memberships_UserId_Active").IsUnique().HasFilter("[Active] = 1");

          model.Entity<OrganizationLocalization>().HasKey(x => x.OrganizationId); Tenant(model.Entity<OrganizationLocalization>());
          model.Entity<OrganizationBranding>().HasKey(x => x.OrganizationId); Tenant(model.Entity<OrganizationBranding>());
          model.Entity<OrganizationSecurityPolicy>().HasKey(x => x.OrganizationId); Tenant(model.Entity<OrganizationSecurityPolicy>());
          // The database holds every stored policy to the bounds Validate enforces on save, whatever wrote the row.
          model.Entity<OrganizationSecurityPolicy>().ToTable(table =>
          {
               foreach (var bound in SecurityPolicyBounds.All)
                    table.HasCheckConstraint($"CK_SecurityPolicies_{bound.Column}", $"[{bound.Column}] BETWEEN {bound.Min} AND {bound.Max}");
          });

          var logo = model.Entity<OrganizationLogo>();
          logo.HasKey(x => x.OrganizationId); Tenant(logo);
          logo.Property(x => x.ContentType).HasMaxLength(50);
          logo.Property(x => x.Data).HasMaxLength(OrganizationLogo.MaxBytes);

          var preference = model.Entity<UserPreference>();
          preference.HasKey(x => new { x.OrganizationId, x.UserId }); Tenant(preference);
          preference.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);

          var role = model.Entity<Role>();
          role.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(role);
          role.Property(x => x.Name).HasMaxLength(100);
          role.HasIndex(x => new { x.OrganizationId, x.Name }).IsUnique();

          var rolePermission = model.Entity<RolePermission>();
          rolePermission.HasKey(x => new { x.OrganizationId, x.RoleId, x.Permission }); Tenant(rolePermission);
          rolePermission.Property(x => x.Permission).HasMaxLength(100);
          rolePermission.HasOne<Role>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.RoleId }).OnDelete(DeleteBehavior.Restrict);

          var personRole = model.Entity<PersonRole>();
          personRole.HasKey(x => new { x.OrganizationId, x.UserId, x.RoleId }); Tenant(personRole);
          personRole.HasOne<Role>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.RoleId }).OnDelete(DeleteBehavior.Restrict);
          personRole.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);
          // One role per person in an organization, as the people screens, tokens and permission checks assume.
          personRole.HasIndex(x => new { x.OrganizationId, x.UserId }).IsUnique();

          var permission = model.Entity<PersonPermissionOverride>();
          permission.HasKey(x => new { x.OrganizationId, x.UserId, x.Permission }); Tenant(permission);
          permission.Property(x => x.Permission).HasMaxLength(100);
          permission.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, x.UserId }).OnDelete(DeleteBehavior.Restrict);

          var audit = model.Entity<AuditEvent>();
          audit.HasKey(x => new { x.OrganizationId, x.Id }); Tenant(audit);
          audit.HasOne<OrganizationMembership>().WithMany().HasForeignKey(x => new { x.OrganizationId, UserId = x.ActorId }).OnDelete(DeleteBehavior.Restrict);
          audit.HasIndex(x => new { x.OrganizationId, x.OccuredAt });
          audit.Property(x => x.Action).HasMaxLength(100);
          audit.Property(x => x.Entity).HasMaxLength(200);
          audit.Property(x => x.CorrelationId).HasMaxLength(100);
     }


     private void ValidateWrites()
     {
          ValidateSetupWrites();
          foreach (var entry in ChangeTracker.Entries().Where(x => x.State is EntityState.Added or EntityState.Modified or EntityState.Deleted))
          {
               if (entry.Entity is AuditEvent && entry.State != EntityState.Added)
                    throw new InvalidOperationException("Audit events are append-only");
               if (entry.Entity is IOrganizationEntity tenant && !Provisioning)
               {
                    if (CurrentOganizationId == Guid.Empty || tenant.OrganizationId != CurrentOganizationId || (entry.State != EntityState.Added && entry.Property(nameof(IOrganizationEntity.OrganizationId)).OriginalValue is Guid original && original != CurrentOganizationId))
                         throw new UnauthorizedAccessException("Cross-organization write rejected.");
               }
               if (entry.Entity is Organization org && !Provisioning && (entry.State == EntityState.Added || org.Id != CurrentOganizationId))
                    throw new UnauthorizedAccessException();
               if (entry.Entity is OrganizationLocalization localization)
                    localization.Validate();
               if (entry.Entity is OrganizationBranding branding)
                    branding.Validate();
               if (entry.Entity is OrganizationSecurityPolicy securityPolicy)
                    securityPolicy.Validate();
               if (entry.Entity is UserPreference userPreference)
                    userPreference.Validate();

               foreach (var property in entry.Properties)
                    if (property.CurrentValue is DateTimeOffset instant && instant.Offset != TimeSpan.Zero)
                         throw new ArgumentException("Instants must be UTC.");
          }
     }

     public override int SaveChanges(bool acceptAllChangesOnSuccess)
     {
          ValidateWrites();
          BumpVersions();
          return base.SaveChanges(acceptAllChangesOnSuccess);
     }

     public override Task<int> SaveChangesAsync(bool acceptAllChangesOnSuccess, CancellationToken cancellationToken = default)
     {
          ValidateWrites();
          BumpVersions();
          return base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
     }
}
