FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Auth.Api.csproj packages.lock.json ./
RUN dotnet restore Auth.Api.csproj --locked-mode
COPY . .
RUN dotnet publish Auth.Api.csproj -c Release --no-restore -o /out /p:UseAppHost=false

# Not a chiseled or Alpine image: the API needs ICU (SqlClient refuses invariant globalization) and tzdata (IANA time zones).
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build /out .
ENV ASPNETCORE_ENVIRONMENT=Production
USER $APP_UID
EXPOSE 8080
# Starting the API never migrates. Each release runs this image once with --migrate before any replica starts.
ENTRYPOINT ["dotnet", "Auth.Api.dll"]
