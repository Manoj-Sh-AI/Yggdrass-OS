package app.yggdras.mobile

// Self-update: installs a downloaded Yggdras APK through Android's PackageInstaller.
// Before installing it checks the file hash, package name, a higher version code and
// that the APK carries exactly the installed app's signing certificate. Android then
// enforces the same key again. Once Yggdras is its own installer of record, Android 12+
// installs without a prompt; otherwise a notification asks for one tap.

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.app.NotificationCompat
import com.facebook.react.ReactPackage
import com.facebook.react.bridge.*
import com.facebook.react.uimanager.ViewManager
import java.io.File
import java.security.MessageDigest

private const val UPDATE_CHANNEL = "yggdras-updates"
private const val INSTALL_STATUS = "app.yggdras.mobile.INSTALL_STATUS"
private const val PREFERENCES = "yggdras.updater"

private fun hex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it) }

private fun fileSha256(file: File): String {
  val digest = MessageDigest.getInstance("SHA-256")
  file.inputStream().use { input ->
    val buffer = ByteArray(1 shl 16)
    while (true) {
      val read = input.read(buffer)
      if (read < 0) break
      digest.update(buffer, 0, read)
    }
  }
  return hex(digest.digest())
}

@Suppress("DEPRECATION")
private fun signers(info: PackageInfo?): Set<String> {
  if (info == null) return emptySet()
  val signatures =
    if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
  return signatures.orEmpty().map { hex(MessageDigest.getInstance("SHA-256").digest(it.toByteArray())) }.toSet()
}

@Suppress("DEPRECATION")
private fun versionCode(info: PackageInfo) =
  if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

@Suppress("DEPRECATION")
private val SIGNING_FLAGS =
  if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES

private fun remember(context: Context, status: String) =
  context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit().putString("last", status).apply()

private fun notifyUpdate(context: Context, text: String, tap: PendingIntent?) {
  val manager = context.getSystemService(NotificationManager::class.java)
  if (Build.VERSION.SDK_INT >= 26)
    manager.createNotificationChannel(
      NotificationChannel(UPDATE_CHANNEL, "App updates", NotificationManager.IMPORTANCE_DEFAULT),
    )
  val open = tap ?: context.packageManager.getLaunchIntentForPackage(context.packageName)?.let {
    PendingIntent.getActivity(context, 19431, it, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
  }
  val notification = NotificationCompat.Builder(context, UPDATE_CHANNEL)
    .setSmallIcon(android.R.drawable.stat_sys_download_done)
    .setContentTitle("Yggdras")
    .setContentText(text)
    .setContentIntent(open)
    .setAutoCancel(true)
    .build()
  try {
    manager.notify(19431, notification)
  } catch (_: SecurityException) {
    // Notifications not allowed: Settings still shows the status.
  }
}

class YggdrasUpdateReceiver : BroadcastReceiver() {
  override fun onReceive(context: Context, intent: Intent) {
    if (intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
      val version = context.packageManager.getPackageInfo(context.packageName, 0).versionName
      remember(context, "updated:$version")
      notifyUpdate(context, "Updated to $version", null)
      return
    }
    if (intent.action != INSTALL_STATUS) return
    when (val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
      PackageInstaller.STATUS_PENDING_USER_ACTION -> {
        @Suppress("DEPRECATION")
        val confirm =
          (if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
          else intent.getParcelableExtra(Intent.EXTRA_INTENT)) ?: return
        confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        remember(context, "needs-tap")
        notifyUpdate(
          context,
          "Tap to finish the Yggdras update",
          PendingIntent.getActivity(context, 19432, confirm, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE),
        )
      }
      PackageInstaller.STATUS_SUCCESS -> remember(context, "installed")
      else -> remember(context, "failed:$status")
    }
  }
}

class YggdrasUpdaterModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  override fun getName() = "YggdrasUpdater"

  @ReactMethod fun canInstall(promise: Promise) {
    promise.resolve(Build.VERSION.SDK_INT < 26 || context.packageManager.canRequestPackageInstalls())
  }

  @ReactMethod fun openInstallSettings() {
    val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.packageName))
      .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(intent)
  }

  @ReactMethod fun lastStatus(promise: Promise) {
    promise.resolve(context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getString("last", null))
  }

  @ReactMethod fun install(uri: String, sha256: String, promise: Promise) {
    try {
      val file = File(Uri.parse(uri).path ?: throw IllegalArgumentException("path"))
      if (!file.isFile || fileSha256(file) != sha256) return promise.reject("hash", "The update file does not match its release.")
      val manager = context.packageManager
      val installed = manager.getPackageInfo(context.packageName, SIGNING_FLAGS)
      val candidate = manager.getPackageArchiveInfo(file.path, SIGNING_FLAGS)
        ?: return promise.reject("apk", "The update is not a readable APK.")
      if (candidate.packageName != context.packageName) return promise.reject("package", "The update is for another app.")
      if (versionCode(candidate) <= versionCode(installed)) return promise.reject("version", "The update is not newer.")
      val mine = signers(installed)
      if (mine.isEmpty() || signers(candidate) != mine) return promise.reject("signer", "The update is not signed with this app's key.")

      val installer = manager.packageInstaller
      val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
      params.setAppPackageName(context.packageName)
      if (Build.VERSION.SDK_INT >= 31)
        params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
      val id = installer.createSession(params)
      installer.openSession(id).use { session ->
        session.openWrite("base.apk", 0, file.length()).use { output ->
          file.inputStream().use { it.copyTo(output) }
          session.fsync(output)
        }
        val status = Intent(context, YggdrasUpdateReceiver::class.java).setAction(INSTALL_STATUS)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
        session.commit(PendingIntent.getBroadcast(context, id, status, flags).intentSender)
      }
      remember(context, "installing")
      promise.resolve(true)
    } catch (error: Exception) {
      promise.reject("install", error.javaClass.simpleName)
    }
  }
}

class YggdrasUpdaterPackage : ReactPackage {
  override fun createNativeModules(context: ReactApplicationContext): List<NativeModule> = listOf(YggdrasUpdaterModule(context))
  override fun createViewManagers(context: ReactApplicationContext): List<ViewManager<*, *>> = emptyList()
}
