FROM mcr.microsoft.com/dotnet/sdk:8.0

WORKDIR /src
COPY Sandbox.Api.csproj ./
RUN dotnet restore
COPY . ./
RUN dotnet publish -c Release -o /app/publish --no-restore

RUN mkdir -p /work /tmp \
 && chmod 1777 /tmp /work

ENV ASPNETCORE_URLS=http://0.0.0.0:8080
ENV ASPNETCORE_CONTENTROOT=/app/publish
ENV DOTNET_CLI_HOME=/tmp
ENV HOME=/tmp
ENV DOTNET_NOLOGO=1
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1

WORKDIR /work
EXPOSE 8080

ENTRYPOINT ["dotnet", "/app/publish/Sandbox.Api.dll"]
