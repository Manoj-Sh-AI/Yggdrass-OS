package app.yggdras.mobile

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.net.Uri
import android.os.*
import android.widget.*
import androidx.core.app.NotificationCompat
import androidx.core.app.Person
import androidx.core.content.ContextCompat
import com.facebook.react.ReactPackage
import com.facebook.react.bridge.*
import com.facebook.react.uimanager.ViewManager
import com.google.firebase.messaging.RemoteMessage
import expo.modules.notifications.service.ExpoFirebaseMessagingService
import java.time.Instant
import java.util.UUID

// Channel sounds cannot change after creation, so the custom ringtone needs a new id.
private const val CHANNEL = "yggdras-calls-v2"
private const val ROUTINE_CHANNEL = "yggdras-routines"
private val RETIRED_CHANNELS = listOf("yggdras-calls")
private const val CLOSED = "app.yggdras.mobile.CALL_CLOSED"
private const val RING = 45000L
private fun notificationId(id: String) = id.hashCode()
private fun ringtoneUri(context: Context) = Uri.parse("android.resource://${context.packageName}/raw/yggdras_ring")
private val ringAttributes = AudioAttributes.Builder()
  .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
  .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()

/** One call channel, created natively so the JS side can never create it with other settings. */
internal fun ensureCallChannel(context: Context) {
  if (Build.VERSION.SDK_INT < 26) return
  val manager = context.getSystemService(NotificationManager::class.java)
  for (old in RETIRED_CHANNELS) manager.deleteNotificationChannel(old)
  if (manager.getNotificationChannel(CHANNEL) != null) return
  val channel = NotificationChannel(CHANNEL, "Calls from Yggdras", NotificationManager.IMPORTANCE_HIGH)
  channel.description = "Rings with the Yggdras chime for scheduled check-ins."
  channel.lockscreenVisibility = Notification.VISIBILITY_PUBLIC
  channel.setSound(ringtoneUri(context), ringAttributes)
  channel.enableVibration(true)
  channel.vibrationPattern = longArrayOf(0, 400, 600, 400, 1600)
  channel.setBypassDnd(false) // Do Not Disturb decides; the app never overrides it.
  manager.createNotificationChannel(channel)
}

private fun action(context: Context, id: String, which: String): PendingIntent {
  val intent = Intent(Intent.ACTION_VIEW, Uri.parse("yggdras://calls/$id?action=$which"), context, MainActivity::class.java)
    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
  return PendingIntent.getActivity(context, (id + which).hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
}
private fun stopRing(context: Context, id: String) {
  CallRinger.stop(id)
  context.getSystemService(NotificationManager::class.java).cancel(notificationId(id))
  context.sendBroadcast(Intent(CLOSED).setPackage(context.packageName).putExtra("callId", id))
}
private fun notificationActive(context: Context, id: String) =
  context.getSystemService(NotificationManager::class.java).activeNotifications.any { it.id == notificationId(id) }

/**
 * Plays the same chime while the app is open and no push notification is sounding
 * (for example before Firebase is configured). Silent when the phone is on silent,
 * vibrate or Do Not Disturb; follows the ring volume the person set.
 */
internal object CallRinger {
  private var player: MediaPlayer? = null
  private var ringing: String? = null
  private val handler = Handler(Looper.getMainLooper())
  fun isRinging(id: String) = synchronized(this) { ringing == id }
  fun start(context: Context, id: String, expiresAt: Long) {
    val remaining = (expiresAt - System.currentTimeMillis()).coerceAtMost(RING)
    if (remaining <= 0 || notificationActive(context, id)) return
    val audio = context.getSystemService(AudioManager::class.java)
    val manager = context.getSystemService(NotificationManager::class.java)
    if (audio.ringerMode != AudioManager.RINGER_MODE_NORMAL) return
    if (manager.currentInterruptionFilter != NotificationManager.INTERRUPTION_FILTER_ALL) return
    synchronized(this) {
      if (ringing == id) return
      release()
      try {
        player = MediaPlayer().apply {
          setAudioAttributes(ringAttributes)
          setDataSource(context, ringtoneUri(context))
          isLooping = true
          prepare()
          start()
        }
        ringing = id
        handler.postDelayed({ stop(id) }, remaining)
      } catch (_: Exception) { release() }
    }
  }
  fun stop(id: String?) = synchronized(this) { if (id == null || ringing == id) release() }
  private fun release() {
    handler.removeCallbacksAndMessages(null)
    try { player?.stop() } catch (_: IllegalStateException) {}
    player?.release(); player = null; ringing = null
  }
}

/** Lets an answered call show over the lock screen; the app turns it off when the call ends. */
object YggdrasLockScreen {
  private val answer = Regex("^yggdras://calls/[a-f0-9-]{36}\\?action=answer$", RegexOption.IGNORE_CASE)
  fun apply(activity: Activity, intent: Intent?) {
    if (answer.matches(intent?.dataString ?: "")) set(activity, true)
  }
  fun set(activity: Activity, value: Boolean) {
    if (Build.VERSION.SDK_INT >= 27) { activity.setShowWhenLocked(value); activity.setTurnScreenOn(value) }
    else {
      @Suppress("DEPRECATION")
      val flags = android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
      if (value) activity.window.addFlags(flags) else activity.window.clearFlags(flags)
    }
  }
}

class YggdrasMessagingService : ExpoFirebaseMessagingService() {
  override fun onMessageReceived(message: RemoteMessage) {
    if (message.data["type"] == "yggdras_routine") {
      showRoutine(message)
      return
    }
    if (message.data["type"] != "yggdras_call") { super.onMessageReceived(message); return }
    val id = message.data["callId"] ?: return
    try { UUID.fromString(id) } catch (_: IllegalArgumentException) { return }
    val seen = getSharedPreferences("yggdras-call-delivery", MODE_PRIVATE)
    if (message.data["state"] != "ringing") {
      seen.edit().putLong("closed_"+id,System.currentTimeMillis()+120000).apply()
      stopRing(this, id); return
    }
    if (seen.getLong("closed_"+id,0)>System.currentTimeMillis()) return
    val expires = try { Instant.parse(message.data["expiresAt"]).toEpochMilli() } catch (_: Exception) { return }
    val remaining = (expires - System.currentTimeMillis()).coerceAtMost(RING)
    if (remaining <= 0) { stopRing(this, id); return }
    if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
    if (seen.getLong(id, 0) >= expires) return
    // Bound the dedupe store: only the current unexpired invitation is necessary.
    val edit=seen.edit()
    for ((key,value) in seen.all) if (value is Long && value<System.currentTimeMillis()) edit.remove(key)
    edit.putLong(id,expires).apply()
    val manager = getSystemService(NotificationManager::class.java)
    ensureCallChannel(this)
    val display = Intent(this, YggdrasIncomingActivity::class.java).putExtra("callId", id).putExtra("expiresAt", expires)
    val full = PendingIntent.getActivity(this, id.hashCode(), display, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    val person = Person.Builder().setName("Yggdras").setImportant(true).build()
    val notification = NotificationCompat.Builder(this, CHANNEL)
      .setSmallIcon(android.R.drawable.sym_call_incoming).setContentTitle("Yggdras is calling")
      .setContentText("A scheduled check-in").setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
      .setCategory(NotificationCompat.CATEGORY_CALL).setPriority(NotificationCompat.PRIORITY_MAX)
      .setSound(ringtoneUri(this), AudioManager.STREAM_RING) // Android 7 and older; the channel decides on 8+
      .setStyle(NotificationCompat.CallStyle.forIncomingCall(person, action(this,id,"decline"), action(this,id,"answer")))
      .setFullScreenIntent(full, true).setOngoing(true).setTimeoutAfter(remaining)
      .setSilent(CallRinger.isRinging(id)) // the open app is already playing the chime
      .build()
    // Insistent: the chime loops until answered, declined, expired or answered elsewhere.
    notification.flags = notification.flags or Notification.FLAG_INSISTENT
    manager.notify(notificationId(id), notification)
  }

  private fun showRoutine(message: RemoteMessage) {
    val id = message.data["deliveryId"] ?: return
    try { UUID.fromString(id) } catch (_: IllegalArgumentException) { return }
    val kind = message.data["kind"] ?: return
    if (kind.length > 40 || !kind.matches(Regex("[a-z_]+"))) return
    val expires = try { Instant.parse(message.data["expiresAt"]).toEpochMilli() } catch (_: Exception) { return }
    val remaining = (expires - System.currentTimeMillis()).coerceAtMost(240000L)
    if (remaining <= 0) return
    if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
    val seen = getSharedPreferences("yggdras-routine-delivery", MODE_PRIVATE)
    if (seen.getLong(id, 0) >= expires) return
    val edit = seen.edit()
    for ((key, value) in seen.all) if (value is Long && value < System.currentTimeMillis()) edit.remove(key)
    edit.putLong(id, expires).apply()
    val manager = getSystemService(NotificationManager::class.java)
    if (Build.VERSION.SDK_INT >= 26 && manager.getNotificationChannel(ROUTINE_CHANNEL) == null) {
      val channel = NotificationChannel(ROUTINE_CHANNEL, "Daily reminders", NotificationManager.IMPORTANCE_DEFAULT)
      channel.description = "Quiet reminders for your daily routine."
      channel.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
      manager.createNotificationChannel(channel)
    }
    fun destination(action: String): PendingIntent {
      val uri = Uri.parse("yggdras://routine/$id?action=$action")
      val intent = Intent(Intent.ACTION_VIEW, uri, this, MainActivity::class.java)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
      return PendingIntent.getActivity(this, (id + action).hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }
    val title = when (kind) {
      "pre_task" -> "Time to start a task"
      "morning" -> "Your morning brief is ready"
      "evening" -> "Time for an evening review"
      "test" -> "Yggdras test reminder"
      else -> "A Yggdras reminder is ready"
    }
    val builder = NotificationCompat.Builder(this, ROUTINE_CHANNEL)
      .setSmallIcon(android.R.drawable.ic_popup_reminder)
      .setContentTitle(title)
      .setContentText("Open Yggdras to see the details.")
      .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
      .setCategory(NotificationCompat.CATEGORY_REMINDER)
      .setContentIntent(destination("open"))
      .setAutoCancel(true)
      .setTimeoutAfter(remaining)
    if (kind == "pre_task") {
      builder.addAction(0, "Started", destination("started"))
      builder.addAction(0, "Not yet", destination("not_yet"))
    }
    manager.notify(notificationId(id), builder.build())
  }
}

class YggdrasIncomingActivity : Activity() {
  private var id = ""
  private val handler = Handler(Looper.getMainLooper())
  private val closed = object : BroadcastReceiver() {
    override fun onReceive(context: Context?, intent: Intent?) { if (intent?.getStringExtra("callId") == id) finish() }
  }
  override fun onCreate(state: Bundle?) {
    super.onCreate(state)
    id = intent.getStringExtra("callId") ?: run { finish(); return }
    val remaining = intent.getLongExtra("expiresAt",0) - System.currentTimeMillis()
    if (remaining <= 0) { finish(); return }
    if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(true); setTurnScreenOn(true) }
    val filter = IntentFilter(CLOSED)
    if (Build.VERSION.SDK_INT >= 33) registerReceiver(closed,filter,Context.RECEIVER_NOT_EXPORTED) else registerReceiver(closed,filter)
    val layout = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; gravity=android.view.Gravity.CENTER; setPadding(48,48,48,48); setBackgroundColor(0xff0c1716.toInt()) }
    layout.addView(TextView(this).apply { text="Yggdras is calling"; textSize=28f; setTextColor(0xfff0f7f2.toInt()) })
    for (which in listOf("answer","decline")) layout.addView(Button(this).apply {
      text=which.replaceFirstChar { it.uppercase() }; minHeight=64
      setOnClickListener { stopRing(this@YggdrasIncomingActivity,this@YggdrasIncomingActivity.id);action(this@YggdrasIncomingActivity,this@YggdrasIncomingActivity.id,which).send();finish() }
    })
    setContentView(layout)
    handler.postDelayed({ finish() },remaining.coerceAtMost(RING))
  }
  override fun onDestroy() { handler.removeCallbacksAndMessages(null);try { unregisterReceiver(closed) } catch (_: IllegalArgumentException) {};super.onDestroy() }
}

class YggdrasAudioService : Service() {
  override fun onBind(intent: Intent?) = null
  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    val manager=getSystemService(NotificationManager::class.java)
    if (Build.VERSION.SDK_INT>=26) manager.createNotificationChannel(NotificationChannel("yggdras-audio","Call in progress",NotificationManager.IMPORTANCE_LOW))
    val notification=NotificationCompat.Builder(this,"yggdras-audio").setSmallIcon(android.R.drawable.sym_call_incoming)
      .setContentTitle("Call with Yggdras").setContentIntent(PendingIntent.getActivity(this,19421,packageManager.getLaunchIntentForPackage(packageName) ?: Intent(this,MainActivity::class.java),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)).setOngoing(true).setCategory(NotificationCompat.CATEGORY_CALL).build()
    startForeground(19421,notification)
    return START_NOT_STICKY
  }
}

class YggdrasCallsModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  override fun getName()="YggdrasCalls"
  @ReactMethod fun startAudioService(promise: Promise) {
    try { ContextCompat.startForegroundService(context,Intent(context,YggdrasAudioService::class.java));promise.resolve(true) }
    catch (_: Exception) { promise.reject("audio_service","Android could not start the call audio service.") }
  }
  @ReactMethod fun stopAudioService() { context.stopService(Intent(context,YggdrasAudioService::class.java)) }
  @ReactMethod fun cancelCallNotification(id: String) { stopRing(context,id) }
  @ReactMethod fun ensureCallChannel() { ensureCallChannel(context) }
  @ReactMethod fun ringInApp(id: String, expiresAt: Double) {
    try { UUID.fromString(id) } catch (_: IllegalArgumentException) { return }
    CallRinger.start(context, id, expiresAt.toLong())
  }
  @ReactMethod fun showOverLockScreen(value: Boolean) {
    val activity = reactApplicationContext.currentActivity ?: return
    activity.runOnUiThread { YggdrasLockScreen.set(activity, value) }
  }
  @ReactMethod fun openFullScreenSettings() {
    if (Build.VERSION.SDK_INT>=34) context.startActivity(Intent("android.settings.MANAGE_APP_USE_FULL_SCREEN_INTENT",Uri.parse("package:${context.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
  }
}
class YggdrasCallsPackage : ReactPackage {
  override fun createNativeModules(context: ReactApplicationContext): List<NativeModule> = listOf(YggdrasCallsModule(context))
  override fun createViewManagers(context: ReactApplicationContext): List<ViewManager<*,*>> = emptyList()
}
