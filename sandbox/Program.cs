using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(o => o.Limits.MaxRequestBodySize = 8 * 1024 * 1024);
builder.Logging.ClearProviders();
builder.Logging.AddConsole();
builder.Services.ConfigureHttpJsonOptions(o =>
{
    o.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
    o.SerializerOptions.PropertyNameCaseInsensitive = true;
    o.SerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
});

var app = builder.Build();
var githubToken = Environment.GetEnvironmentVariable("GH_TOKEN") ?? "";
var githubRepo = Environment.GetEnvironmentVariable("GITHUB_REPO") ?? "ashkandehnavi/n8n-code";
var githubApi = Environment.GetEnvironmentVariable("GITHUB_API") ?? "https://api.github.com";
Paths.CliHomeDir = Directory.Exists("/tmp") ? "/tmp" : Path.GetTempPath();
Paths.WorkRoot = Environment.GetEnvironmentVariable("SANDBOX_WORK_DIR") ?? "";
if (string.IsNullOrWhiteSpace(Paths.WorkRoot))
{
    Paths.WorkRoot = Directory.Exists("/work") ? "/work" : Path.Combine(Paths.CliHomeDir, "csharp-sandbox-work");
}
Directory.CreateDirectory(Paths.WorkRoot);

app.UseDefaultFiles();
app.UseStaticFiles();
var jsonOpts = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    PropertyNameCaseInsensitive = true,
    WriteIndented = false
};

app.MapGet("/health", () => Results.Json(new
{
    ok = true,
    service = "csharp-sandbox",
    runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription
}));

app.MapGet("/meta", () => Results.Json(new
{
    ok = true,
    ui = true,
    github_configured = !string.IsNullOrWhiteSpace(githubToken),
    github_repo = githubRepo
}));

app.MapPost("/execute", async (ExecuteRequest req, CancellationToken ct) =>
{
    var timeout = Math.Clamp(req.TimeoutSeconds <= 0 ? 60 : req.TimeoutSeconds, 5, 120);
    var runId = SanitizeId(string.IsNullOrWhiteSpace(req.RunId) ? Guid.NewGuid().ToString("N") : req.RunId);
    var work = Path.Combine(Paths.WorkRoot, runId);
    var started = Stopwatch.StartNew();

    try
    {
        if (req.Files is null || req.Files.Count == 0)
        {
            return Results.Json(Fail("no files provided", started), jsonOpts);
        }

        PrepareWorkspace(work, req.Files);
        EnsureProjectFile(work, req.Kind);

        var restore = await RunDotnet(work, ["restore", "--disable-parallel"], 90, ct);
        if (restore.ExitCode != 0)
        {
            return Results.Json(new ExecuteResponse
            {
                Ok = false,
                Stage = "restore",
                ExitCode = restore.ExitCode,
                Stdout = restore.Stdout,
                Stderr = restore.Stderr,
                DurationMs = started.ElapsedMilliseconds,
                RunId = runId
            }, jsonOpts);
        }

        var build = await RunDotnet(work, ["build", "--no-restore", "-c", "Release"], 90, ct);
        if (build.ExitCode != 0)
        {
            return Results.Json(new ExecuteResponse
            {
                Ok = false,
                Stage = "build",
                ExitCode = build.ExitCode,
                Stdout = Trim(build.Stdout + "\n" + restore.Stdout),
                Stderr = Trim(build.Stderr),
                DurationMs = started.ElapsedMilliseconds,
                RunId = runId
            }, jsonOpts);
        }

        var kind = string.IsNullOrWhiteSpace(req.Kind) ? DetectKind(work) : req.Kind!.Trim().ToLowerInvariant();
        CommandResult run;
        string? httpProbe = null;

        if (kind == "web")
        {
            var port = 5055 + Math.Abs(runId.GetHashCode()) % 20;
            run = await RunWebProject(work, port, timeout, ct);
            httpProbe = run.HttpBody;
        }
        else
        {
            run = await RunDotnet(work, ["run", "--no-build", "-c", "Release", "--no-restore"], timeout, ct);
        }

        var ok = run.ExitCode == 0 && !run.TimedOut;
        return Results.Json(new ExecuteResponse
        {
            Ok = ok,
            Stage = kind == "web" ? "run-web" : "run",
            Kind = kind,
            ExitCode = run.ExitCode,
            TimedOut = run.TimedOut,
            Stdout = Trim(run.Stdout),
            Stderr = Trim(run.Stderr),
            HttpBody = httpProbe,
            DurationMs = started.ElapsedMilliseconds,
            RunId = runId
        }, jsonOpts);
    }
    catch (Exception ex)
    {
        return Results.Json(new ExecuteResponse
        {
            Ok = false,
            Stage = "sandbox",
            ExitCode = -1,
            Stderr = ex.Message,
            DurationMs = started.ElapsedMilliseconds,
            RunId = runId
        }, jsonOpts);
    }
    finally
    {
        try { Directory.Delete(work, true); } catch { /* leftover workdirs are cleaned on next boot */ }
    }
});

app.MapPost("/github/publish", async (PublishRequest req, CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(githubToken))
    {
        return Results.Json(new PublishResponse { Ok = false, Error = "GH_TOKEN is not configured" }, jsonOpts);
    }

    if (req.Files is null || req.Files.Count == 0)
    {
        return Results.Json(new PublishResponse { Ok = false, Error = "no files provided" }, jsonOpts);
    }

    var runId = SanitizeId(string.IsNullOrWhiteSpace(req.RunId) ? Guid.NewGuid().ToString("N") : req.RunId);
    var branch = $"agent/{runId}";
    var gh = new GitHubClient(githubApi, githubToken, githubRepo);

    try
    {
        await gh.EnsureMainAsync(ct);
        var mainSha = await gh.GetBranchShaAsync("main", ct);
        await gh.CreateBranchAsync(branch, mainSha, ct);

        var prefix = $"generated/{runId}";
        foreach (var (rel, content) in req.Files)
        {
            var safe = SanitizeRelPath(rel);
            await gh.PutFileAsync(branch, $"{prefix}/{safe}", content ?? "", $"feat({runId}): add {safe}", ct);
        }

        if (!string.IsNullOrWhiteSpace(req.ReportMd))
        {
            await gh.PutFileAsync(branch, $"{prefix}/REPORT.md", req.ReportMd, $"docs({runId}): add run report", ct);
        }

        var title = string.IsNullOrWhiteSpace(req.Title)
            ? $"Generated C# app {runId}"
            : req.Title.Trim();
        var body = string.IsNullOrWhiteSpace(req.Body)
            ? $"Automated PR from the n8n coding agent.\n\nRun: `{runId}`"
            : req.Body;
        var pr = await gh.CreatePullRequestAsync(title, body, branch, "main", ct);

        return Results.Json(new PublishResponse
        {
            Ok = true,
            Repo = githubRepo,
            Branch = branch,
            PrUrl = pr.HtmlUrl,
            PrNumber = pr.Number
        }, jsonOpts);
    }
    catch (Exception ex)
    {
        return Results.Json(new PublishResponse { Ok = false, Error = ex.Message, Branch = branch }, jsonOpts);
    }
});

app.Run();

static ExecuteResponse Fail(string error, Stopwatch started) => new()
{
    Ok = false,
    Stage = "validate",
    ExitCode = -1,
    Stderr = error,
    DurationMs = started.ElapsedMilliseconds
};

static string SanitizeId(string raw)
{
    var cleaned = Regex.Replace(raw, @"[^a-zA-Z0-9_-]", "");
    return string.IsNullOrEmpty(cleaned) ? Guid.NewGuid().ToString("N")[..12] : cleaned[..Math.Min(cleaned.Length, 40)];
}

static string SanitizeRelPath(string path)
{
    var normalized = path.Replace('\\', '/').Trim().TrimStart('/');
    if (normalized.Contains("..", StringComparison.Ordinal) || Path.IsPathRooted(normalized))
    {
        throw new InvalidOperationException($"unsafe path: {path}");
    }

    var ext = Path.GetExtension(normalized).ToLowerInvariant();
    var allowed = new HashSet<string> { ".cs", ".csproj", ".sln", ".json", ".md", ".txt", ".http", ".props", ".targets", ".gitignore" };
    if (!string.IsNullOrEmpty(ext) && !allowed.Contains(ext))
    {
        throw new InvalidOperationException($"file type not allowed: {ext}");
    }

    return normalized;
}

static void PrepareWorkspace(string work, Dictionary<string, string> files)
{
    if (Directory.Exists(work)) Directory.Delete(work, true);
    Directory.CreateDirectory(work);

    foreach (var (rel, content) in files)
    {
        var safe = SanitizeRelPath(rel);
        var full = Path.Combine(work, safe);
        Directory.CreateDirectory(Path.GetDirectoryName(full)!);
        File.WriteAllText(full, content ?? "", Encoding.UTF8);
    }
}

static void EnsureProjectFile(string work, string? kind)
{
    if (Directory.EnumerateFiles(work, "*.csproj", SearchOption.AllDirectories).Any()) return;

    var isWeb = string.Equals(kind, "web", StringComparison.OrdinalIgnoreCase) || DetectKind(work) == "web";
    var csproj = isWeb
        ? """
        <Project Sdk="Microsoft.NET.Sdk.Web">
          <PropertyGroup>
            <TargetFramework>net8.0</TargetFramework>
            <Nullable>enable</Nullable>
            <ImplicitUsings>enable</ImplicitUsings>
          </PropertyGroup>
        </Project>
        """
        : """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup>
            <OutputType>Exe</OutputType>
            <TargetFramework>net8.0</TargetFramework>
            <ImplicitUsings>enable</ImplicitUsings>
            <Nullable>enable</Nullable>
          </PropertyGroup>
        </Project>
        """;
    File.WriteAllText(Path.Combine(work, "App.csproj"), csproj);
}

static string DetectKind(string work)
{
    foreach (var file in Directory.EnumerateFiles(work, "*.cs", SearchOption.AllDirectories))
    {
        var text = File.ReadAllText(file);
        if (text.Contains("WebApplication.CreateBuilder", StringComparison.Ordinal)
            || text.Contains("MapGet(", StringComparison.Ordinal)
            || text.Contains("UseRouting", StringComparison.Ordinal))
        {
            return "web";
        }
    }

    return "console";
}

static async Task<CommandResult> RunDotnet(string work, string[] args, int timeoutSeconds, CancellationToken ct)
{
    var psi = new ProcessStartInfo("dotnet")
    {
        WorkingDirectory = work,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        UseShellExecute = false,
        CreateNoWindow = true
    };
    foreach (var a in args) psi.ArgumentList.Add(a);
    psi.Environment["DOTNET_CLI_HOME"] = Paths.CliHomeDir;
    psi.Environment["HOME"] = Paths.CliHomeDir;
    psi.Environment["DOTNET_NOLOGO"] = "1";
    psi.Environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1";

    using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
    var stdout = new StringBuilder();
    var stderr = new StringBuilder();
    proc.OutputDataReceived += (_, e) => { if (e.Data != null) stdout.AppendLine(e.Data); };
    proc.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };

    proc.Start();
    proc.BeginOutputReadLine();
    proc.BeginErrorReadLine();

    using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
    timeoutCts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
    try
    {
        await proc.WaitForExitAsync(timeoutCts.Token);
        return new CommandResult(proc.ExitCode, stdout.ToString(), stderr.ToString(), false, null);
    }
    catch (OperationCanceledException)
    {
        TryKill(proc);
        return new CommandResult(-1, stdout.ToString(), stderr.ToString() + "\n[sandbox] timed out", true, null);
    }
}

static async Task<CommandResult> RunWebProject(string work, int port, int timeoutSeconds, CancellationToken ct)
{
    var psi = new ProcessStartInfo("dotnet")
    {
        WorkingDirectory = work,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        UseShellExecute = false,
        CreateNoWindow = true
    };
    psi.ArgumentList.Add("run");
    psi.ArgumentList.Add("--no-build");
    psi.ArgumentList.Add("-c");
    psi.ArgumentList.Add("Release");
    psi.ArgumentList.Add("--no-restore");
    psi.Environment["DOTNET_CLI_HOME"] = Paths.CliHomeDir;
    psi.Environment["HOME"] = Paths.CliHomeDir;
    psi.Environment["ASPNETCORE_URLS"] = $"http://127.0.0.1:{port}";
    psi.Environment["ASPNETCORE_ENVIRONMENT"] = "Production";

    using var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
    var stdout = new StringBuilder();
    var stderr = new StringBuilder();
    proc.OutputDataReceived += (_, e) => { if (e.Data != null) stdout.AppendLine(e.Data); };
    proc.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };
    proc.Start();
    proc.BeginOutputReadLine();
    proc.BeginErrorReadLine();

    var deadline = DateTime.UtcNow.AddSeconds(Math.Min(timeoutSeconds, 45));
    string? body = null;
    using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
    while (DateTime.UtcNow < deadline && !proc.HasExited)
    {
        try
        {
            var resp = await http.GetAsync($"http://127.0.0.1:{port}/", ct);
            body = $"HTTP {(int)resp.StatusCode}\n{await resp.Content.ReadAsStringAsync(ct)}";
            break;
        }
        catch
        {
            await Task.Delay(400, ct);
        }
    }

    TryKill(proc);
    var ok = body != null;
    return new CommandResult(ok ? 0 : (proc.HasExited ? proc.ExitCode : -1), stdout.ToString(), stderr.ToString(), false, body);
}

static void TryKill(Process proc)
{
    try { if (!proc.HasExited) proc.Kill(entireProcessTree: true); } catch { /* ignore */ }
}

static string Trim(string? text)
{
    if (string.IsNullOrEmpty(text)) return "";
    const int max = 12000;
    return text.Length <= max ? text : text[..max] + "\n...[truncated]";
}

sealed record CommandResult(int ExitCode, string Stdout, string Stderr, bool TimedOut, string? HttpBody);

sealed class ExecuteRequest
{
    public Dictionary<string, string>? Files { get; set; }
    public int TimeoutSeconds { get; set; } = 60;
    public string? RunId { get; set; }
    public string? Kind { get; set; }
}

sealed class ExecuteResponse
{
    public bool Ok { get; set; }
    public string? Stage { get; set; }
    public string? Kind { get; set; }
    public int ExitCode { get; set; }
    public bool TimedOut { get; set; }
    public string? Stdout { get; set; }
    public string? Stderr { get; set; }
    public string? HttpBody { get; set; }
    public long DurationMs { get; set; }
    public string? RunId { get; set; }
}

sealed class PublishRequest
{
    public Dictionary<string, string>? Files { get; set; }
    public string? RunId { get; set; }
    public string? Title { get; set; }
    public string? Body { get; set; }
    public string? ReportMd { get; set; }
}

sealed class PublishResponse
{
    public bool Ok { get; set; }
    public string? Repo { get; set; }
    public string? Branch { get; set; }
    public string? PrUrl { get; set; }
    public int? PrNumber { get; set; }
    public string? Error { get; set; }
}

sealed class GitHubClient
{
    private readonly HttpClient _http;
    private readonly string _repo;

    public GitHubClient(string api, string token, string repo)
    {
        _repo = repo;
        _http = new HttpClient { BaseAddress = new Uri(api.TrimEnd('/') + "/") };
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("n8n-coding-agent-sandbox");
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        _http.DefaultRequestHeaders.Add("X-GitHub-Api-Version", "2022-11-28");
    }

    public async Task EnsureMainAsync(CancellationToken ct)
    {
        var resp = await _http.GetAsync($"repos/{_repo}/commits?sha=main&per_page=1", ct);
        if (resp.IsSuccessStatusCode) return;

        var readme = """
            # n8n-code

            Generated C# apps from the n8n multi-agent coding workflow land in `generated/` via pull requests.
            """;
        await PutFileAsync("main", "README.md", readme, "chore: initialize repository", ct);
    }

    public async Task<string> GetBranchShaAsync(string branch, CancellationToken ct)
    {
        using var doc = await ReadJson($"repos/{_repo}/git/ref/heads/{branch}", ct);
        return doc.RootElement.GetProperty("object").GetProperty("sha").GetString()
               ?? throw new InvalidOperationException("missing sha");
    }

    public async Task CreateBranchAsync(string branch, string sha, CancellationToken ct)
    {
        var payload = JsonSerializer.Serialize(new { @ref = $"refs/heads/{branch}", sha });
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        var resp = await _http.PostAsync($"repos/{_repo}/git/refs", content, ct);
        if (resp.IsSuccessStatusCode) return;
        var body = await resp.Content.ReadAsStringAsync(ct);
        if ((int)resp.StatusCode == 422 && body.Contains("already exists", StringComparison.OrdinalIgnoreCase)) return;
        throw new InvalidOperationException($"create branch failed: {(int)resp.StatusCode} {body}");
    }

    public async Task PutFileAsync(string branch, string path, string text, string message, CancellationToken ct)
    {
        string? sha = null;
        var existing = await _http.GetAsync($"repos/{_repo}/contents/{path}?ref={Uri.EscapeDataString(branch)}", ct);
        if (existing.IsSuccessStatusCode)
        {
            using var doc = JsonDocument.Parse(await existing.Content.ReadAsStringAsync(ct));
            sha = doc.RootElement.GetProperty("sha").GetString();
        }

        var payloadObj = new Dictionary<string, object?>
        {
            ["message"] = message,
            ["content"] = Convert.ToBase64String(Encoding.UTF8.GetBytes(text)),
            ["branch"] = branch
        };
        if (!string.IsNullOrEmpty(sha)) payloadObj["sha"] = sha;

        using var content = new StringContent(JsonSerializer.Serialize(payloadObj), Encoding.UTF8, "application/json");
        var resp = await _http.PutAsync($"repos/{_repo}/contents/{path}", content, ct);
        if (!resp.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"put file {path} failed: {(int)resp.StatusCode} {await resp.Content.ReadAsStringAsync(ct)}");
        }
    }

    public async Task<(string HtmlUrl, int Number)> CreatePullRequestAsync(string title, string body, string head, string @base, CancellationToken ct)
    {
        var payload = JsonSerializer.Serialize(new { title, body, head, @base });
        using var content = new StringContent(payload, Encoding.UTF8, "application/json");
        var resp = await _http.PostAsync($"repos/{_repo}/pulls", content, ct);
        var text = await resp.Content.ReadAsStringAsync(ct);
        if (!resp.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"create PR failed: {(int)resp.StatusCode} {text}");
        }

        using var doc = JsonDocument.Parse(text);
        return (
            doc.RootElement.GetProperty("html_url").GetString() ?? "",
            doc.RootElement.GetProperty("number").GetInt32()
        );
    }

    private async Task<JsonDocument> ReadJson(string path, CancellationToken ct)
    {
        var resp = await _http.GetAsync(path, ct);
        var text = await resp.Content.ReadAsStringAsync(ct);
        if (!resp.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"GET {path} failed: {(int)resp.StatusCode} {text}");
        }

        return JsonDocument.Parse(text);
    }
}

static class Paths
{
    public static string WorkRoot = "/work";
    public static string CliHomeDir = "/tmp";
}
