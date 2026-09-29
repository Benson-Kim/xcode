using Auth.Application.Setup;
using Auth.Domain;
using Auth.Domain.Setup;
using Auth.Infrastructure;

namespace Auth.Application;

// What a scoped person may see of other people and of their data scopes. The people list, the people editor and the
// change log all use these rules, so someone hidden in one place is hidden in all of them.
public static class PeopleVisibility
{
    // The people the actor may see, as a query, so filtering, ordering and paging run in the database. Visible are the
    // actor themself; everyone, for an all-companies actor; anyone whose company scope meets the actor's companies or
    // the companies of the actor's vehicles; and anyone whose vehicle scope holds a vehicle the actor can see
    // (CanSeeVehicle). People without a role are never listed.
    public static IQueryable<OrganizationMembership> People(AuthDb db, SetupActor actor)
    {
        var people = db.Memberships.Where(m => db.PersonRoles.Any(r => r.UserId == m.UserId));
        if (actor.AllCompanies)
            return people;

        var companyIds = actor.CompanyIds.ToList();
        var vehicleIds = actor.VehicleIds.ToList();
        var vehicles = db.Set<FleetVehicle>();
        var companiesOfActorVehicles = vehicles.Where(v => vehicleIds.Contains(v.Id)).Select(v => v.CompanyId);
        var visibleVehicles = vehicles.Where(v => vehicleIds.Contains(v.Id) || companyIds.Contains(v.CompanyId)).Select(v => v.Id);
        return people.Where(m =>
            m.UserId == actor.UserId ||
            db.SetupCompanyScopes.Any(s => s.UserId == m.UserId && (companyIds.Contains(s.CompanyId) || companiesOfActorVehicles.Contains(s.CompanyId))) ||
            db.SetupVehicleScopes.Any(s => s.UserId == m.UserId && visibleVehicles.Contains(s.VehicleId)));
    }

    // A company in the actor's own data scope, which they may see in someone's scope and hand on.
    public static bool CanSeeCompany(SetupActor actor, Guid companyId) =>
        actor.AllCompanies || actor.CompanyIds.Contains(companyId);

    // A vehicle in the actor's own data scope: one of their vehicles, or one in their companies.
    public static bool CanSeeVehicle(SetupActor actor, Guid vehicleId, Guid companyId) =>
        actor.AllCompanies || actor.VehicleIds.Contains(vehicleId) || actor.CompanyIds.Contains(companyId);
}
