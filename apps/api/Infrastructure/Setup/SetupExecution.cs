using Auth.Application;
using Auth.Domain.Setup;
using Microsoft.EntityFrameworkCore;

namespace Auth.Infrastructure.Setup;

/// <summary>Adapts setup commands to the Phase 1 template-method pipeline.</summary>


public sealed class SetupExecution(IOrganizationContext context, IOrganizationRepository organizations, IUnitOfWork unitOfWork, AuthDb db, IClock clock) : ISetupExecution
{
     public Task<T> Read<T>(string permission, Func<SetupActor, Task<T>> query, CancellationToken ct)
         => new Invocation<T>(context, organizations, unitOfWork, permission, async ()
         => await query(await Actor(ct))).Run(true, ct);

     public Task<T> Write<T>(string permission, Func<SetupActor, Task<T>> command, CancellationToken ct)
         => new Invocation<T>(context, organizations, unitOfWork, permission, async ()
         => await command(await Actor(ct))).Run(true, ct);

     private async Task<SetupActor> Actor(CancellationToken ct)
     {
          var scope = await db
               .Set<SetupDataScope>()
               .AsNoTracking()
               .SingleOrDefaultAsync(x => x.UserId == context.ActorId, ct);
          var companies = await db
               .Set<SetupCompanyScope>()
               .AsNoTracking().Where(x => x.UserId == context.ActorId)
               .Select(x => x.CompanyId)
               .ToListAsync(ct);
          var vehicles = await db
               .Set<SetupVehicleScope>()
               .AsNoTracking()
               .Where(x => x.UserId == context.ActorId)
               .Select(x => x.VehicleId)
               .ToListAsync(ct);

          // Business dates use the organization zone, never the editor's personal override.
          var zone = await db
               .Localizations
               .AsNoTracking()
               .Select(x => x.TimeZone)
               .SingleOrDefaultAsync(ct) ?? "Africa/Nairobi";
          var calendarDate = DateOnly
               .FromDateTime(TimeZoneInfo.ConvertTime(clock.UtcNow, TimeZoneInfo.FindSystemTimeZoneById(zone)).DateTime);
          var businessDate = await db.Organizations
               .AsNoTracking()
               .Select(x => x.BusinessDate)
               .SingleAsync(ct);
          // All setup calculations use the organization's accounting date, never a browser or user-local date.
          var today = businessDate ?? calendarDate;

          return new(context.OrganizationId, context.ActorId, today, scope?.AllCompanies == true, companies, vehicles, context.CorrelationId);
     }

     private sealed class Invocation<T>(IOrganizationContext context, IOrganizationRepository repository, IUnitOfWork unitOfWork, string permission, Func<Task<T>> execute) : OrganizationUseCase<bool, T>(context, repository, unitOfWork)
     {
          protected override string RequiredPermission => permission;
          protected override void Validate(bool request) { }
          protected override Task<T> Execute(bool request, CancellationToken ct) => execute();
     }
}