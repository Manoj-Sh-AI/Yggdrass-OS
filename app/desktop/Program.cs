// Windows laptop host. Application behavior and all data stay in the shared API.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace YggdrasDesktop {
    public class DesktopConfig {
        public string python { get; set; }
        public string moduleRoot { get; set; }
        public string dataRoot { get; set; }
        // Set when Yggdras is hosted (Railway): the window opens this HTTPS address and
        // starts nothing on this laptop. Unset: the laptop runtime as before.
        public string url { get; set; }
    }
    public class ServiceStatus {
        public bool ready { get; set; }
        public string origin { get; set; }
    }
    static class Program {
        public static string VerifyOutput;
        [STAThread]
        static int Main(string[] args) {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && args[0] == "--verify") VerifyOutput = Path.GetFullPath(args[1]);
            bool created;
            string suffix = VerifyOutput == null ? "main" : Guid.NewGuid().ToString("N");
            using (var mutex = new Mutex(true, "Local\\YggdrasDesktop." + suffix, out created)) {
                if (!created) {
                    try { using (var signal = EventWaitHandle.OpenExisting("Local\\YggdrasDesktop.activate")) signal.Set(); }
                    catch (WaitHandleCannotBeOpenedException) { }
                    return 0;
                }
                try {
                    Application.Run(new WorkspaceWindow());
                    return 0;
                } catch (Exception) {
                    if (VerifyOutput == null) MessageBox.Show("Yggdras could not open. Check the local application log and try again.", "Yggdras", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return 1;
                }
            }
        }
    }

    sealed class WorkspaceWindow : Form {
        WebView2 view = new WebView2();
        readonly Label status = new Label();
        readonly Button retry = new Button();
        readonly JavaScriptSerializer json = new JavaScriptSerializer();
        readonly System.Windows.Forms.Timer health = new System.Windows.Forms.Timer();
        EventWaitHandle activate;
        DesktopConfig config;
        Uri origin;
        bool opening, closing;
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);

        public WorkspaceWindow() {
            Text = "Yggdras";
            BackColor = Color.FromArgb(19, 29, 28);
            ForeColor = Color.FromArgb(231, 237, 229);
            Size = new Size(1440, 960);
            MinimumSize = new Size(420, 600);
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            view.Dock = DockStyle.Fill;
            view.DefaultBackgroundColor = BackColor;
            view.Visible = false;
            status.Text = "Opening Yggdras…";
            status.Font = new Font("Segoe UI", 16);
            status.AutoSize = true;
            status.Location = new Point(36, 48);
            retry.Text = "Try again";
            retry.AutoSize = true;
            retry.Location = new Point(40, 105);
            retry.Visible = false;
            retry.Click += async (sender, args) => await OpenWorkspace();
            Controls.Add(view); Controls.Add(status); Controls.Add(retry);
            Shown += async (sender, args) => {
                try { int dark = 1; DwmSetWindowAttribute(Handle, 20, ref dark, 4); } catch (DllNotFoundException) { }
                await OpenWorkspace();
            };
            FormClosing += (sender, args) => { closing = true; health.Stop(); };
            FormClosed += (sender, args) => { if (activate != null) activate.Dispose(); view.Dispose(); };
            if (Program.VerifyOutput != null) {
                Opacity = 0; ShowInTaskbar = false;
                var timeout = new System.Windows.Forms.Timer { Interval = 120000 };
                timeout.Tick += (sender, args) => { timeout.Stop(); File.WriteAllText(Program.VerifyOutput + ".error", "Desktop verification timed out."); Close(); };
                timeout.Start();
            } else {
                activate = new EventWaitHandle(false, EventResetMode.AutoReset, "Local\\YggdrasDesktop.activate");
                Task.Run(() => {
                    while (!closing) {
                        if (activate.WaitOne(1000) && !closing) BeginInvoke(new Action(() => { if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal; Show(); Activate(); }));
                    }
                });
            }
            health.Interval = 15000;
            health.Tick += async (sender, args) => {
                if (opening || origin == null || Hosted) return;  // a hosted app has no local service
                try {
                    var result = await Runtime("status");
                    if (!result.ready) ShowFailure("The local service stopped. Your saved data is preserved.");
                } catch (Exception) { ShowFailure("The local service is unavailable. Your saved data is preserved."); }
            };
        }

        DesktopConfig Config() {
            if (config != null) return config;
            var loaded = json.Deserialize<DesktopConfig>(File.ReadAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "desktop.json")));
            if (!Directory.Exists(loaded.dataRoot)) throw new InvalidOperationException();
            if (String.IsNullOrEmpty(loaded.url)) {
                if (!File.Exists(loaded.python) || !Directory.Exists(loaded.moduleRoot)) throw new InvalidOperationException();
            } else {
                Uri hosted;
                // Only an exact HTTPS origin: no path, no credentials.
                if (!Uri.TryCreate(loaded.url, UriKind.Absolute, out hosted) || hosted.Scheme != "https" || !String.IsNullOrEmpty(hosted.UserInfo) || hosted.AbsolutePath != "/") throw new InvalidOperationException();
            }
            return config = loaded;
        }

        bool Hosted { get { return !String.IsNullOrEmpty(Config().url); } }

        async Task<ServiceStatus> Runtime(string action) {
            Config();
            var start = new ProcessStartInfo(config.python) {
                Arguments = "-m yggdress_app.local_runtime --home \"" + config.dataRoot + "\" " + action,
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
                WorkingDirectory = config.moduleRoot
            };
            start.EnvironmentVariables["PYTHONPATH"] = config.moduleRoot;
            using (var process = Process.Start(start)) {
                var output = process.StandardOutput.ReadToEndAsync();
                var error = process.StandardError.ReadToEndAsync();
                // Never log returned credentials, environment or subprocess errors.
                await Task.Run(() => process.WaitForExit());
                await error;
                if (process.ExitCode != 0) throw new InvalidOperationException();
                var result = json.Deserialize<ServiceStatus>(await output);
                if (result.ready && result.origin != "http://127.0.0.1:3000") throw new InvalidOperationException();
                return result;
            }
        }

        async Task OpenWorkspace() {
            if (opening) return;
            opening = true; retry.Visible = false;
            status.Text = "Opening Yggdras…"; status.Visible = true;
            try {
                if (Hosted) {
                    origin = new Uri(Config().url);
                } else {
                    var service = await Runtime("ensure");
                    if (!service.ready) throw new InvalidOperationException();
                    origin = new Uri(service.origin);
                }
                if (view.CoreWebView2 == null) {
                    var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(config.dataRoot, "webview"));
                    await view.EnsureCoreWebView2Async(environment);
                    view.CoreWebView2.Settings.IsWebMessageEnabled = false;
                    view.CoreWebView2.Settings.AreHostObjectsAllowed = false;
                    view.CoreWebView2.Settings.AreDevToolsEnabled = false;
                    view.CoreWebView2.Settings.IsStatusBarEnabled = false;
                    view.CoreWebView2.Settings.IsGeneralAutofillEnabled = false;
                    view.CoreWebView2.Settings.IsPasswordAutosaveEnabled = false;
                    view.CoreWebView2.NavigationStarting += (sender, args) => {
                        if (!Local(args.Uri)) { args.Cancel = true; External(args.Uri); }
                    };
                    view.CoreWebView2.FrameNavigationStarting += (sender, args) => { if (!Local(args.Uri) && args.Uri != "about:blank") args.Cancel = true; };
                    view.CoreWebView2.NewWindowRequested += (sender, args) => { args.Handled = true; External(args.Uri); };
                    view.CoreWebView2.PermissionRequested += (sender, args) => {
                        // Calls with Yggdras need the microphone: granted to the app's own origin only.
                        if (args.PermissionKind == CoreWebView2PermissionKind.Microphone && Local(args.Uri)) { args.State = CoreWebView2PermissionState.Allow; return; }
                        // Never save a refusal: a saved Deny stops this handler from being asked again.
                        if (args.PermissionKind != CoreWebView2PermissionKind.Geolocation) { args.SavesInProfile = false; args.State = CoreWebView2PermissionState.Deny; }
                    };
                    // An older build saved a microphone Deny in this profile; replace it for our own origin.
                    view.CoreWebView2.Profile.SetPermissionStateAsync(CoreWebView2PermissionKind.Microphone, origin.GetLeftPart(UriPartial.Authority), CoreWebView2PermissionState.Allow);
                    view.CoreWebView2.ProcessFailed += (sender, args) => {
                        ShowFailure("The display stopped. Reopen your workspace; saved data is preserved.");
                        if (args.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited) {
                            Controls.Remove(view); view.Dispose();
                            view = new WebView2 { Dock = DockStyle.Fill, Visible = false, DefaultBackgroundColor = BackColor };
                            Controls.Add(view); status.BringToFront(); retry.BringToFront();
                        }
                    };
                    view.CoreWebView2.NavigationCompleted += async (sender, args) => {
                        if (!args.IsSuccess) { ShowFailure("Could not display your workspace. Try again."); return; }
                        status.Visible = false; retry.Visible = false; view.Visible = true;
                        if (Program.VerifyOutput != null) {
                            try {
                                await Task.Delay(1500);
                                var result = await view.CoreWebView2.ExecuteScriptAsync("JSON.stringify({title:document.title,path:location.pathname,heading:document.querySelector('h1')?.textContent,bridge:typeof window.chrome?.webview?.postMessage})");
                                File.WriteAllText(Program.VerifyOutput, result);
                                using (var image = File.Create(Program.VerifyOutput + ".png")) await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, image);
                            } catch (Exception) { File.WriteAllText(Program.VerifyOutput + ".error", "Native rendering verification failed."); }
                            finally { Close(); }
                        }
                    };
                }
                view.CoreWebView2.Navigate(new Uri(origin, "/today").ToString());
                health.Start();
            } catch (Exception) {
                ShowFailure(config != null && !String.IsNullOrEmpty(config.url)
                    ? "Yggdras could not be reached. Check the internet connection, then try again."
                    : "Yggdras could not start. Check that this laptop’s local services are available, then try again.");
                if (Program.VerifyOutput != null) { File.WriteAllText(Program.VerifyOutput + ".error", "Desktop startup failed."); Close(); }
            } finally { opening = false; }
        }

        bool Local(string value) {
            Uri target;
            return Uri.TryCreate(value, UriKind.Absolute, out target) && target.Scheme == origin.Scheme && target.Host == origin.Host && target.Port == origin.Port && String.IsNullOrEmpty(target.UserInfo);
        }
        void External(string value) {
            Uri target;
            if (!Uri.TryCreate(value, UriKind.Absolute, out target)) return;
            if (Local(value)) { view.CoreWebView2.Navigate(value); return; }
            if (target.Scheme == "https" || target.Scheme == "http") {
                try { Process.Start(new ProcessStartInfo(target.AbsoluteUri) { UseShellExecute = true }); } catch (Exception) { }
            }
        }
        void ShowFailure(string message) {
            health.Stop(); view.Visible = false; status.Text = message;
            status.MaximumSize = new Size(Math.Max(300, ClientSize.Width - 80), 0);
            status.Visible = true; retry.Top = status.Bottom + 24; retry.Visible = true;
        }
    }
}
