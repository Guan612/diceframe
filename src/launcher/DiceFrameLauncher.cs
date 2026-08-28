using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

internal static class DiceFrameLauncher
{
    private const string DefaultPort = "18000";
    private const int ReadyTimeoutSeconds = 60;
    private const int ProbationDefaultSeconds = 90;
    private const int ProbationMinSeconds = 10;
    private const int ProbationMaxSeconds = 600;
    private const int ProbationFailureGraceSeconds = 20;
    private static Process serverProcess;
    private static bool shuttingDown;
    // 本机 DiceFrame endpoint 解析结果：数据目录 + 端口 → scheme 与自签指纹。
    private static string launcherDataDir = "";
    private static string launcherPort = DefaultPort;
    // 仅对 Launcher → 本机 DiceFrame 生效的证书指纹固定；绝不做全局校验关闭。
    private static string expectedCertFingerprint = "";
    private static HttpClient localHttpClient;

    [STAThread]
    private static int Main(string[] args)
    {
        Console.Title = "DiceFrame";

        string installRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
        string dataDir = Path.Combine(installRoot, "data");
        string logsDir = Path.Combine(installRoot, "logs");
        string updaterDir = Path.Combine(dataDir, "_updater");
        string restartSignal = Path.Combine(updaterDir, "restart_signal.json");
        string currentPointer = Path.Combine(updaterDir, "current.json");

        Directory.CreateDirectory(dataDir);
        Directory.CreateDirectory(logsDir);
        Directory.CreateDirectory(updaterDir);
        TryDelete(Path.Combine(installRoot, "DiceFrame.exe.old"));

        string port = ResolvePort(Path.Combine(dataDir, "config.json"));
        launcherDataDir = dataDir;
        launcherPort = port;
        InitLocalHttpClient();
        string url = ResolveServerEndpoint().Url;
        string activeDir = ResolveActiveDirectory(installRoot, currentPointer);
        MigrateLegacyPortablePayload(
            installRoot,
            currentPointer,
            restartSignal,
            activeDir
        );

        Console.WriteLine("========================================");
        Console.WriteLine("  DiceFrame Portable");
        Console.WriteLine("  " + url);
        Console.WriteLine("========================================");
        Console.WriteLine();

        AppDomain.CurrentDomain.ProcessExit += delegate { StopServer(); };
        Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs eventArgs)
        {
            eventArgs.Cancel = true;
            shuttingDown = true;
            StopServer();
            Environment.Exit(0);
        };

        try
        {
            serverProcess = StartServer(installRoot, activeDir, dataDir);
        }
        catch (Exception ex)
        {
            return Fail("DiceFrame failed to start: " + ex.Message);
        }

        if (WaitForServer(serverProcess, url, TimeSpan.FromSeconds(ReadyTimeoutSeconds)))
        {
            OpenBrowser(url);
            Console.WriteLine("DiceFrame is running. Close this window to stop it.");
            Console.WriteLine();
        }
        else if (serverProcess.HasExited)
        {
            return Fail("DiceFrame exited before the Web UI became ready.");
        }
        else
        {
            Console.WriteLine("DiceFrame is still starting. Open this address manually:");
            Console.WriteLine(url);
            Console.WriteLine();
        }

        while (!shuttingDown)
        {
            if (File.Exists(restartSignal))
            {
                activeDir = HandleUpdate(
                    installRoot,
                    dataDir,
                    updaterDir,
                    currentPointer,
                    restartSignal,
                    activeDir,
                    url
                );
            }

            if (serverProcess == null || serverProcess.HasExited)
            {
                return serverProcess == null ? 1 : serverProcess.ExitCode;
            }
            Thread.Sleep(500);
        }
        return 0;
    }

    private static string HandleUpdate(
        string installRoot,
        string dataDir,
        string updaterDir,
        string currentPointer,
        string restartSignal,
        string previousDir,
        string url
    )
    {
        string signal;
        try
        {
            signal = File.ReadAllText(restartSignal, Encoding.UTF8);
        }
        catch (Exception ex)
        {
            WriteUpdateState(
                updaterDir,
                "failed",
                "",
                "无法读取更新重启信号：" + ex.Message
            );
            TryDelete(restartSignal);
            return previousDir;
        }

        string version = JsonString(signal, "expected_version");
        string candidateDir = JsonString(signal, "candidate_dir");
        string launcherPath = JsonString(signal, "launcher_path");
        int probationSeconds = JsonInt(signal, "probation_seconds", ProbationDefaultSeconds);
        probationSeconds = Math.Max(
            ProbationMinSeconds,
            Math.Min(probationSeconds, ProbationMaxSeconds)
        );

        string validationError = ValidateCandidate(
            installRoot,
            candidateDir,
            launcherPath,
            version
        );
        if (validationError != null)
        {
            WriteUpdateState(updaterDir, "failed", version, validationError);
            TryDelete(restartSignal);
            return previousDir;
        }

        Console.WriteLine("Applying DiceFrame " + version + "...");
        StopServer();

        Process candidateProcess = null;
        string failure = "";
        try
        {
            candidateProcess = StartServer(installRoot, candidateDir, dataDir);
            serverProcess = candidateProcess;
            // 数据目录是共享的：候选版本启动后重新解析 scheme（HTTP/HTTPS）。
            url = ResolveServerEndpoint().Url;
            if (!WaitForVersion(
                candidateProcess,
                url,
                version,
                TimeSpan.FromSeconds(ReadyTimeoutSeconds)
            ))
            {
                failure = candidateProcess.HasExited
                    ? "候选版本在健康检查前退出"
                    : "候选版本健康检查超时或版本不匹配";
            }
            else if (!PassesProbation(
                candidateProcess,
                url,
                version,
                probationSeconds
            ))
            {
                failure = "候选版本在观察期内退出或失去响应";
            }
        }
        catch (Exception ex)
        {
            failure = "候选版本启动失败：" + ex.Message;
        }

        if (string.IsNullOrEmpty(failure))
        {
            string relativeDir = RelativeVersionDirectory(installRoot, candidateDir);
            string versionsDir = Path.Combine(installRoot, "versions");
            string previousRelativeDir = IsUnder(previousDir, versionsDir)
                ? RelativeVersionDirectory(installRoot, previousDir)
                : "";
            AtomicWriteText(
                currentPointer,
                "{\n"
                    + "  \"schema\": 1,\n"
                    + "  \"version\": \"" + JsonEscape(version) + "\",\n"
                    + "  \"relative_dir\": \"" + JsonEscape(relativeDir) + "\",\n"
                    + "  \"previous_relative_dir\": \""
                    + JsonEscape(previousRelativeDir)
                    + "\"\n"
                    + "}\n"
            );
            PromoteLauncher(installRoot, launcherPath);
            PruneOldVersions(installRoot, candidateDir, previousDir);
            WriteUpdateState(updaterDir, "done", version, "");
            TryDelete(restartSignal);
            Console.WriteLine("Update to " + version + " succeeded.");
            return candidateDir;
        }

        Console.WriteLine("Update failed; rolling back: " + failure);
        StopProcess(candidateProcess);
        try
        {
            serverProcess = StartServer(installRoot, previousDir, dataDir);
            url = ResolveServerEndpoint().Url;
            if (!WaitForServer(serverProcess, url, TimeSpan.FromSeconds(ReadyTimeoutSeconds)))
            {
                WriteUpdateState(
                    updaterDir,
                    "failed",
                    version,
                    failure + "；回滚版本也未能恢复服务"
                );
            }
            else
            {
                WriteUpdateState(updaterDir, "rolled-back", version, failure);
                Console.WriteLine("Rollback succeeded.");
            }
        }
        catch (Exception ex)
        {
            serverProcess = null;
            WriteUpdateState(
                updaterDir,
                "failed",
                version,
                failure + "；回滚启动失败：" + ex.Message
            );
        }
        TryDelete(restartSignal);
        return previousDir;
    }

    private static Process StartServer(
        string installRoot,
        string activeDir,
        string dataDir
    )
    {
        string python = Path.Combine(activeDir, "python", "python.exe");
        string serverScript = Path.Combine(activeDir, "app", "web_server.py");
        if (!File.Exists(python))
        {
            throw new FileNotFoundException("Cannot find bundled Python", python);
        }
        if (!File.Exists(serverScript))
        {
            throw new FileNotFoundException("Cannot find DiceFrame server", serverScript);
        }

        ProcessStartInfo info = new ProcessStartInfo();
        info.FileName = python;
        info.Arguments = Quote(serverScript);
        info.WorkingDirectory = installRoot;
        info.UseShellExecute = false;
        info.EnvironmentVariables["TRPG_DATA_DIR"] = dataDir;
        info.EnvironmentVariables["TRPG_INSTALL_ROOT"] = installRoot;
        info.EnvironmentVariables["TRPG_ACTIVE_VERSION_DIR"] = activeDir;
        return Process.Start(info);
    }

    private static string ResolveActiveDirectory(
        string installRoot,
        string currentPointer
    )
    {
        try
        {
            if (File.Exists(currentPointer))
            {
                string json = File.ReadAllText(currentPointer, Encoding.UTF8);
                string current = ResolveVersionDirectory(
                    installRoot,
                    JsonString(json, "relative_dir")
                );
                if (!string.IsNullOrEmpty(current))
                {
                    return current;
                }

                string previous = ResolveVersionDirectory(
                    installRoot,
                    JsonString(json, "previous_relative_dir")
                );
                if (!string.IsNullOrEmpty(previous))
                {
                    Console.WriteLine(
                        "Current version is unavailable; using the previous version."
                    );
                    return previous;
                }
            }
        }
        catch
        {
        }
        return installRoot;
    }

    private static string ResolveVersionDirectory(
        string installRoot,
        string relativeDir
    )
    {
        try
        {
            if (string.IsNullOrEmpty(relativeDir) || Path.IsPathRooted(relativeDir))
            {
                return null;
            }
            string candidate = Path.GetFullPath(Path.Combine(installRoot, relativeDir));
            if (
                IsUnder(candidate, Path.Combine(installRoot, "versions"))
                && HasPortablePayload(candidate)
            )
            {
                return candidate;
            }
        }
        catch
        {
        }
        return null;
    }

    private static bool HasPortablePayload(string directory)
    {
        return File.Exists(Path.Combine(directory, "python", "python.exe"))
            && File.Exists(Path.Combine(directory, "app", "web_server.py"));
    }

    private static void MigrateLegacyPortablePayload(
        string installRoot,
        string currentPointer,
        string restartSignal,
        string activeDir
    )
    {
        try
        {
            if (
                !HasPortablePayload(installRoot)
                || !File.Exists(currentPointer)
                || File.Exists(restartSignal)
            )
            {
                return;
            }

            string pointerJson = File.ReadAllText(currentPointer, Encoding.UTF8);
            string currentRelative = JsonString(pointerJson, "relative_dir");
            string current = ResolveVersionDirectory(installRoot, currentRelative);
            if (
                string.IsNullOrEmpty(current)
                || !string.Equals(
                    Path.GetFullPath(activeDir),
                    Path.GetFullPath(current),
                    StringComparison.OrdinalIgnoreCase
                )
            )
            {
                return;
            }

            string previousRelative = JsonString(
                pointerJson,
                "previous_relative_dir"
            );
            string previous = ResolveVersionDirectory(
                installRoot,
                previousRelative
            );
            if (!string.IsNullOrEmpty(previous))
            {
                if (string.Equals(
                    previous,
                    current,
                    StringComparison.OrdinalIgnoreCase
                ))
                {
                    return;
                }
                DeleteLegacyPayload(Path.Combine(installRoot, "app"));
                DeleteLegacyPayload(Path.Combine(installRoot, "python"));
                return;
            }
            if (!string.IsNullOrEmpty(previousRelative))
            {
                return;
            }

            string updaterState = Path.Combine(
                Path.GetDirectoryName(currentPointer),
                "state.json"
            );
            if (!File.Exists(updaterState))
            {
                return;
            }
            string stateJson = File.ReadAllText(updaterState, Encoding.UTF8);
            string version = JsonString(pointerJson, "version");
            if (
                !string.Equals(
                    JsonString(stateJson, "state"),
                    "done",
                    StringComparison.OrdinalIgnoreCase
                )
                || string.IsNullOrEmpty(version)
                || !string.Equals(
                    JsonString(stateJson, "version"),
                    version,
                    StringComparison.OrdinalIgnoreCase
                )
            )
            {
                return;
            }

            string versionsDir = Path.Combine(installRoot, "versions");
            string inferredPrevious = null;
            foreach (string directory in Directory.GetDirectories(versionsDir))
            {
                string candidate = Path.GetFullPath(directory);
                if (
                    string.Equals(
                        candidate,
                        current,
                        StringComparison.OrdinalIgnoreCase
                    )
                    || !HasPortablePayload(candidate)
                )
                {
                    continue;
                }
                if (!string.IsNullOrEmpty(inferredPrevious))
                {
                    return;
                }
                inferredPrevious = candidate;
            }
            if (string.IsNullOrEmpty(inferredPrevious))
            {
                return;
            }

            AtomicWriteText(
                currentPointer,
                "{\n"
                    + "  \"schema\": 1,\n"
                    + "  \"version\": \"" + JsonEscape(version) + "\",\n"
                    + "  \"relative_dir\": \""
                    + JsonEscape(currentRelative)
                    + "\",\n"
                    + "  \"previous_relative_dir\": \""
                    + JsonEscape(
                        RelativeVersionDirectory(
                            installRoot,
                            inferredPrevious
                        )
                    )
                    + "\"\n"
                    + "}\n"
            );
            DeleteLegacyPayload(Path.Combine(installRoot, "app"));
            DeleteLegacyPayload(Path.Combine(installRoot, "python"));
            Console.WriteLine(
                "Migrated the legacy portable layout to two version slots."
            );
        }
        catch (Exception ex)
        {
            Console.WriteLine(
                "Could not migrate the legacy portable layout: " + ex.Message
            );
        }
    }

    private static string ValidateCandidate(
        string installRoot,
        string candidateDir,
        string launcherPath,
        string version
    )
    {
        if (string.IsNullOrEmpty(version))
        {
            return "重启信号缺少目标版本";
        }
        if (
            string.IsNullOrEmpty(candidateDir)
            || !IsUnder(candidateDir, Path.Combine(installRoot, "versions"))
        )
        {
            return "候选版本目录无效";
        }
        if (
            !File.Exists(Path.Combine(candidateDir, "python", "python.exe"))
            || !File.Exists(Path.Combine(candidateDir, "app", "web_server.py"))
        )
        {
            return "候选版本文件不完整";
        }
        if (
            string.IsNullOrEmpty(launcherPath)
            || !IsUnder(launcherPath, Path.Combine(installRoot, "data", "_updater"))
            || !File.Exists(launcherPath)
        )
        {
            return "候选启动器无效";
        }
        return null;
    }

    private static bool PassesProbation(
        Process process,
        string url,
        string version,
        int seconds
    )
    {
        DateTime deadline = DateTime.UtcNow.AddSeconds(seconds);
        DateTime nextHealthCheck = DateTime.MinValue;
        DateTime failureStarted = DateTime.MinValue;
        TimeSpan failureGrace = TimeSpan.FromSeconds(ProbationFailureGraceSeconds);
        while (DateTime.UtcNow < deadline)
        {
            if (process == null || process.HasExited)
            {
                return false;
            }
            if (DateTime.UtcNow >= nextHealthCheck)
            {
                if (IsHealthyVersion(url, version))
                {
                    failureStarted = DateTime.MinValue;
                }
                else
                {
                    if (failureStarted == DateTime.MinValue)
                    {
                        failureStarted = DateTime.UtcNow;
                    }
                    else if (DateTime.UtcNow - failureStarted >= failureGrace)
                    {
                        return false;
                    }
                }
                nextHealthCheck = DateTime.UtcNow.AddSeconds(2);
            }
            Thread.Sleep(500);
        }
        return true;
    }

    private static bool WaitForServer(
        Process process,
        string url,
        TimeSpan timeout
    )
    {
        DateTime deadline = DateTime.UtcNow.Add(timeout);
        while (DateTime.UtcNow < deadline)
        {
            if (process != null && process.HasExited)
            {
                return false;
            }
            if (CanOpen(url))
            {
                return true;
            }
            Thread.Sleep(500);
        }
        return false;
    }

    private static bool WaitForVersion(
        Process process,
        string url,
        string expectedVersion,
        TimeSpan timeout
    )
    {
        DateTime deadline = DateTime.UtcNow.Add(timeout);
        while (DateTime.UtcNow < deadline)
        {
            if (process != null && process.HasExited)
            {
                return false;
            }
            if (IsHealthyVersion(url, expectedVersion))
            {
                return true;
            }
            Thread.Sleep(500);
        }
        return false;
    }

    private static bool IsHealthyVersion(string baseUrl, string expectedVersion)
    {
        try
        {
            string body = HttpGet(baseUrl + "/api/system/update/health");
            return JsonString(body, "version") == expectedVersion;
        }
        catch
        {
            return false;
        }
    }

    private static bool CanOpen(string url)
    {
        try
        {
            using (
                HttpResponseMessage response = localHttpClient
                    .GetAsync(url, HttpCompletionOption.ResponseHeadersRead)
                    .GetAwaiter()
                    .GetResult()
            )
            {
                int statusCode = (int)response.StatusCode;
                return statusCode >= 200 && statusCode < 500;
            }
        }
        catch
        {
            return false;
        }
    }

    private static string HttpGet(string url)
    {
        using (
            HttpResponseMessage response = localHttpClient
                .GetAsync(url)
                .GetAwaiter()
                .GetResult()
        )
        using (
            StreamReader reader = new StreamReader(
                response.Content.ReadAsStreamAsync().GetAwaiter().GetResult(),
                Encoding.UTF8
            )
        )
        {
            string body = reader.ReadToEnd();
            if ((int)response.StatusCode < 200 || (int)response.StatusCode >= 300)
            {
                throw new WebException("HTTP " + (int)response.StatusCode);
            }
            return body;
        }
    }

    // ---- 本机 endpoint 与证书验证 ----

    private sealed class ServerEndpoint
    {
        public string Url;
        public string Fingerprint;
    }

    /// <summary>
    /// 统一解析本机 DiceFrame endpoint：HTTP 保持旧行为；本地 HTTPS 按指纹文件固定。
    /// WaitForServer、更新健康检查、OpenBrowser 都走这里，不各自拼接 scheme。
    /// </summary>
    private static ServerEndpoint ResolveServerEndpoint()
    {
        string url = "http://127.0.0.1:" + launcherPort;
        string fingerprint = "";
        try
        {
            string configPath = Path.Combine(launcherDataDir, "config.json");
            if (File.Exists(configPath))
            {
                string text = File.ReadAllText(configPath);
                bool selfSigned = Regex
                    .Match(text, "\"tls_mode\"\\s*:\\s*\"self_signed\"")
                    .Success;
                if (selfSigned)
                {
                    string fingerprintPath = Path.Combine(
                        launcherDataDir,
                        "certs",
                        "self-signed",
                        "fingerprint.txt"
                    );
                    if (File.Exists(fingerprintPath))
                    {
                        string recorded = File.ReadAllText(fingerprintPath).Trim();
                        if (recorded.Length > 0)
                        {
                            url = "https://127.0.0.1:" + launcherPort;
                            fingerprint = recorded;
                        }
                    }
                    // 指纹文件缺失（例如服务端回退 HTTP）时保持 http：
                    // 宁可健康检查失败，也不做未验证的 HTTPS 信任。
                }
            }
        }
        catch
        {
        }
        expectedCertFingerprint = fingerprint;
        return new ServerEndpoint { Url = url, Fingerprint = fingerprint };
    }

    private static void InitLocalHttpClient()
    {
        WebRequestHandler handler = new WebRequestHandler();
        // 只影响本机 DiceFrame 请求的 handler；更新、GitHub 等其它流量不走它。
        handler.ServerCertificateValidationCallback = delegate(
            object sender,
            X509Certificate certificate,
            X509Chain chain,
            SslPolicyErrors errors
        )
        {
            return ValidateLocalCertificate(certificate, errors);
        };
        handler.CachePolicy = new System.Net.Cache.RequestCachePolicy(
            System.Net.Cache.RequestCacheLevel.NoCacheNoStore
        );
        localHttpClient = new HttpClient(handler);
        localHttpClient.Timeout = TimeSpan.FromSeconds(2);
    }

    private static bool ValidateLocalCertificate(
        X509Certificate certificate,
        SslPolicyErrors errors
    )
    {
        if (errors == SslPolicyErrors.None)
        {
            // 系统信任链验证通过（未来的 Let's Encrypt 证书走这里）。
            return true;
        }
        // 自签证书：只有指纹与本地记录完全一致时才信任。
        string expected = expectedCertFingerprint;
        if (expected.Length == 0 || certificate == null)
        {
            return false;
        }
        string normalized = expected.Replace(":", "").Replace("-", "").ToUpperInvariant();
        return Sha256Hex(certificate.GetRawCertData()) == normalized;
    }

    private static string Sha256Hex(byte[] data)
    {
        using (SHA256 sha = SHA256.Create())
        {
            byte[] hash = sha.ComputeHash(data);
            StringBuilder builder = new StringBuilder(hash.Length * 2);
            foreach (byte value in hash)
            {
                builder.Append(value.ToString("X2"));
            }
            return builder.ToString();
        }
    }

    private static void PromoteLauncher(string installRoot, string stagedLauncher)
    {
        string launcher = Path.Combine(installRoot, "DiceFrame.exe");
        string oldLauncher = launcher + ".old";
        try
        {
            TryDelete(oldLauncher);
            if (File.Exists(launcher))
            {
                File.Move(launcher, oldLauncher);
            }
            File.Copy(stagedLauncher, launcher, true);
            TryDelete(stagedLauncher);
        }
        catch (Exception ex)
        {
            Console.WriteLine("Launcher replacement deferred: " + ex.Message);
            try
            {
                if (!File.Exists(launcher) && File.Exists(oldLauncher))
                {
                    File.Move(oldLauncher, launcher);
                }
            }
            catch
            {
            }
        }
    }

    private static void WriteUpdateState(
        string updaterDir,
        string state,
        string version,
        string error
    )
    {
        string json = "{\n"
            + "  \"state\": \"" + JsonEscape(state) + "\",\n"
            + "  \"version\": \"" + JsonEscape(version) + "\",\n"
            + "  \"error\": \"" + JsonEscape(error) + "\",\n"
            + "  \"restart_needed\": false,\n"
            + "  \"completed_at\": "
            + DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(
                CultureInfo.InvariantCulture
            )
            + "\n}\n";
        AtomicWriteText(Path.Combine(updaterDir, "state.json"), json);
    }

    private static void AtomicWriteText(string path, string content)
    {
        string temp = path + ".tmp";
        string backup = path + ".bak";
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        File.WriteAllText(temp, content, new UTF8Encoding(false));
        if (File.Exists(path))
        {
            TryDelete(backup);
            File.Replace(temp, path, backup, true);
            TryDelete(backup);
        }
        else
        {
            File.Move(temp, path);
        }
    }

    private static string JsonString(string json, string key)
    {
        Match match = Regex.Match(
            json ?? "",
            "\"" + Regex.Escape(key) + "\"\\s*:\\s*\"((?:\\\\.|[^\"])*)\""
        );
        return match.Success ? JsonUnescape(match.Groups[1].Value) : "";
    }

    private static int JsonInt(string json, string key, int fallback)
    {
        Match match = Regex.Match(
            json ?? "",
            "\"" + Regex.Escape(key) + "\"\\s*:\\s*(-?\\d+)"
        );
        int value;
        return match.Success && int.TryParse(match.Groups[1].Value, out value)
            ? value
            : fallback;
    }

    private static string JsonUnescape(string value)
    {
        StringBuilder output = new StringBuilder();
        for (int index = 0; index < value.Length; index++)
        {
            char current = value[index];
            if (current != '\\' || index + 1 >= value.Length)
            {
                output.Append(current);
                continue;
            }
            char escaped = value[++index];
            if (escaped == '"' || escaped == '\\' || escaped == '/')
            {
                output.Append(escaped);
            }
            else if (escaped == 'b')
            {
                output.Append('\b');
            }
            else if (escaped == 'f')
            {
                output.Append('\f');
            }
            else if (escaped == 'n')
            {
                output.Append('\n');
            }
            else if (escaped == 'r')
            {
                output.Append('\r');
            }
            else if (escaped == 't')
            {
                output.Append('\t');
            }
            else if (escaped == 'u' && index + 4 < value.Length)
            {
                string hex = value.Substring(index + 1, 4);
                int code;
                if (int.TryParse(
                    hex,
                    NumberStyles.HexNumber,
                    CultureInfo.InvariantCulture,
                    out code
                ))
                {
                    output.Append((char)code);
                    index += 4;
                }
            }
            else
            {
                output.Append(escaped);
            }
        }
        return output.ToString();
    }

    private static string JsonEscape(string value)
    {
        if (value == null)
        {
            return "";
        }
        StringBuilder output = new StringBuilder();
        foreach (char current in value)
        {
            switch (current)
            {
                case '"':
                    output.Append("\\\"");
                    break;
                case '\\':
                    output.Append("\\\\");
                    break;
                case '\n':
                    output.Append("\\n");
                    break;
                case '\r':
                    output.Append("\\r");
                    break;
                case '\t':
                    output.Append("\\t");
                    break;
                default:
                    if (current < 32)
                    {
                        output.Append("\\u");
                        output.Append(((int)current).ToString("x4"));
                    }
                    else
                    {
                        output.Append(current);
                    }
                    break;
            }
        }
        return output.ToString();
    }

    private static bool IsUnder(string path, string parent)
    {
        try
        {
            string fullPath = Path.GetFullPath(path).TrimEnd(
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar
            );
            string fullParent = Path.GetFullPath(parent).TrimEnd(
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar
            );
            return fullPath.StartsWith(
                fullParent + Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase
            );
        }
        catch
        {
            return false;
        }
    }

    private static void PruneOldVersions(
        string installRoot,
        string currentDir,
        string previousDir
    )
    {
        string versionsDir = Path.Combine(installRoot, "versions");
        try
        {
            if (!Directory.Exists(versionsDir))
            {
                return;
            }

            string current = Path.GetFullPath(currentDir);
            string previous = Path.GetFullPath(previousDir);
            foreach (string directory in Directory.GetDirectories(versionsDir))
            {
                string candidate = Path.GetFullPath(directory);
                bool keepCurrent = string.Equals(
                    candidate,
                    current,
                    StringComparison.OrdinalIgnoreCase
                );
                bool keepPrevious = IsUnder(previous, versionsDir)
                    && string.Equals(
                        candidate,
                        previous,
                        StringComparison.OrdinalIgnoreCase
                    );
                if (!keepCurrent && !keepPrevious && IsUnder(candidate, versionsDir))
                {
                    try
                    {
                        Directory.Delete(candidate, true);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine(
                            "Could not remove old version "
                                + candidate
                                + ": "
                                + ex.Message
                        );
                    }
                }
            }

            bool hasVersionRollbackPair = IsUnder(current, versionsDir)
                && IsUnder(previous, versionsDir)
                && !string.Equals(
                    current,
                    previous,
                    StringComparison.OrdinalIgnoreCase
                )
                && HasPortablePayload(current)
                && HasPortablePayload(previous);
            if (hasVersionRollbackPair)
            {
                DeleteLegacyPayload(Path.Combine(installRoot, "app"));
                DeleteLegacyPayload(Path.Combine(installRoot, "python"));
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine("Could not prune old versions: " + ex.Message);
        }
    }

    private static void DeleteLegacyPayload(string directory)
    {
        try
        {
            if (Directory.Exists(directory))
            {
                Directory.Delete(directory, true);
                Console.WriteLine("Removed legacy portable payload " + directory);
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine(
                "Could not remove legacy portable payload "
                    + directory
                    + ": "
                    + ex.Message
            );
        }
    }

    private static string RelativeVersionDirectory(
        string installRoot,
        string candidateDir
    )
    {
        string root = Path.GetFullPath(installRoot).TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
        string candidate = Path.GetFullPath(candidateDir);
        return candidate.Substring(root.Length).TrimStart(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        );
    }

    private static void OpenBrowser(string url)
    {
        try
        {
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = url;
            info.UseShellExecute = true;
            Process.Start(info);
        }
        catch
        {
            Console.WriteLine("Open this address in your browser:");
            Console.WriteLine(url);
        }
    }

    private static void StopServer()
    {
        StopProcess(serverProcess);
    }

    private static void StopProcess(Process process)
    {
        try
        {
            if (process != null && !process.HasExited)
            {
                process.Kill();
                process.WaitForExit(3000);
            }
        }
        catch
        {
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
        }
    }

    private static string ResolvePort(string configPath)
    {
        string envPort = Environment.GetEnvironmentVariable("TRPG_WEB_PORT");
        if (IsPort(envPort))
        {
            return envPort;
        }
        try
        {
            if (File.Exists(configPath))
            {
                string text = File.ReadAllText(configPath);
                Match match = Regex.Match(text, "\"web_port\"\\s*:\\s*(\\d+)");
                if (match.Success && IsPort(match.Groups[1].Value))
                {
                    return match.Groups[1].Value;
                }
            }
        }
        catch
        {
        }
        return DefaultPort;
    }

    private static bool IsPort(string value)
    {
        int port;
        return !string.IsNullOrWhiteSpace(value)
            && int.TryParse(value, out port)
            && port >= 1
            && port <= 65535;
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static int Fail(string message)
    {
        Console.WriteLine(message);
        Console.WriteLine();
        Console.WriteLine("Press any key to close.");
        Console.ReadKey(true);
        return 1;
    }
}
