package com.crashguard.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.util.Log
import com.crashguard.core.CrashDetector
import com.crashguard.core.Evaluation
import com.crashguard.core.Model
import com.google.android.gms.wearable.Wearable

class CrashService : Service(), SensorEventListener, LocationListener {
    companion object {
        const val ACTION_CANCEL = "com.crashguard.CANCEL"
        const val ACTION_STOP = "com.crashguard.STOP"
        const val ACTION_SIMULATE = "com.crashguard.SIMULATE"
        const val ACTION_WATCH_ALERT = "com.crashguard.WATCH_ALERT"
        const val ACTION_TICK = "com.crashguard.TICK"      // broadcast to AlertActivity
        const val EXTRA_REMAINING = "remaining"
        const val EXTRA_PHASE = "phase"                    // counting | sent | cancelled
        @Volatile var running = false
    }

    private lateinit var detector: CrashDetector
    private lateinit var prefs: Prefs
    private val handler = Handler(Looper.getMainLooper())
    private var wake: PowerManager.WakeLock? = null
    private var lastLoc: Location? = null
    private var alerting = false
    private var dryForced = false
    private var deadlineMs = 0L
    private var probability = 0.0
    private var incidentId: String? = null
    private var sent = false

    private val ticker = object : Runnable {
        override fun run() {
            detector.tick(SystemClock.elapsedRealtimeNanos())
            if (alerting) tickAlert()
            else if (sent) lastLoc?.let { Escalator.pushLocation(prefs, incidentId, it) }
            handler.postDelayed(this, 1000)
        }
    }

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        val model = Model.fromJson(assets.open("crash_model.json").bufferedReader().readText())
        detector = CrashDetector(model) { onEvaluated(it) }
        channels()
        val n = monitorNotification()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        else startForeground(1, n)
        val sm = getSystemService(SensorManager::class.java)
        sm.registerListener(this, sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER), 5000)
        sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.let { sm.registerListener(this, it, 5000) }
        runCatching {
            getSystemService(LocationManager::class.java)
                .requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, this)
        }.onFailure { Log.w("CrashGuard", "no location permission/GPS", it) }
        wake = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "crashguard:monitor").apply { acquire() }
        handler.post(ticker)
        running = true
    }

    override fun onStartCommand(i: Intent?, flags: Int, startId: Int): Int {
        when (i?.action) {
            ACTION_CANCEL -> cancelAlert()
            ACTION_STOP -> stopSelf()
            ACTION_SIMULATE -> startAlert(0.99, forceDry = true)
            ACTION_WATCH_ALERT -> if (!alerting) startAlert(i.getDoubleExtra("p", 0.9), false)
        }
        return START_STICKY
    }

    override fun onSensorChanged(e: SensorEvent) {
        when (e.sensor.type) {
            Sensor.TYPE_ACCELEROMETER ->
                detector.onAccelerometer(e.timestamp, e.values[0].toDouble(), e.values[1].toDouble(), e.values[2].toDouble())
            Sensor.TYPE_GYROSCOPE ->
                detector.onGyroscope(e.values[0].toDouble(), e.values[1].toDouble(), e.values[2].toDouble())
        }
    }

    override fun onAccuracyChanged(s: Sensor?, a: Int) {}

    override fun onLocationChanged(l: Location) {
        lastLoc = l
        if (l.hasSpeed()) detector.onSpeed(l.elapsedRealtimeNanos, l.speed.toDouble())
    }

    private fun onEvaluated(ev: Evaluation) {
        Log.i("CrashGuard", "trigger p=${"%.3f".format(ev.probability)} peak=${"%.1f".format(ev.peakG)}g positive=${ev.positive}")
        EventLog.save(this, ev)
        if (ev.positive && !alerting) handler.post { startAlert(ev.probability, false) }
    }

    private fun startAlert(p: Double, forceDry: Boolean) {
        alerting = true; sent = false; dryForced = forceDry; probability = p; incidentId = null
        deadlineMs = SystemClock.elapsedRealtime() + prefs.countdownSec * 1000L
        val full = PendingIntent.getActivity(this, 0, Intent(this, AlertActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE)
        val n = Notification.Builder(this, "alert").setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Crash detected").setContentText("Tap to cancel - alert sends in ${prefs.countdownSec}s")
            .setCategory(Notification.CATEGORY_ALARM).setFullScreenIntent(full, true).setContentIntent(full)
            .setOngoing(true).build()
        getSystemService(NotificationManager::class.java).notify(2, n)
        runCatching { startActivity(Intent(this, AlertActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        buzz()
        sendToWatch("/crashguard/countdown", prefs.countdownSec.toString())
        tickAlert()
    }

    private fun tickAlert() {
        val left = ((deadlineMs - SystemClock.elapsedRealtime()) / 1000).toInt()
        if (left > 0) { broadcast("counting", left); buzz(); return }
        alerting = false; sent = true
        incidentId = Escalator.run(this, prefs, lastLoc, probability, dryForced)
        broadcast("sent", 0)
        EventLog.labelLast(this, "escalated")
    }

    private fun cancelAlert() {
        alerting = false; sent = false
        Escalator.cancelIncident(prefs, incidentId)
        EventLog.labelLast(this, "cancelled_by_user")
        getSystemService(NotificationManager::class.java).cancel(2)
        broadcast("cancelled", 0)
        sendToWatch("/crashguard/cancelled", "")
        detector.reset(SystemClock.elapsedRealtimeNanos())
    }

    private fun broadcast(phase: String, left: Int) = sendBroadcast(
        Intent(ACTION_TICK).setPackage(packageName).putExtra(EXTRA_PHASE, phase).putExtra(EXTRA_REMAINING, left))

    private fun buzz() {
        val v = getSystemService(Vibrator::class.java)
        if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createOneShot(600, 255))
        else @Suppress("DEPRECATION") v.vibrate(600)
    }

    private fun sendToWatch(path: String, payload: String) {
        Wearable.getNodeClient(this).connectedNodes.addOnSuccessListener { nodes ->
            nodes.forEach { Wearable.getMessageClient(this).sendMessage(it.id, path, payload.toByteArray()) }
        }
    }

    private fun channels() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("monitor", "Monitoring", NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel("alert", "Crash alert", NotificationManager.IMPORTANCE_HIGH))
    }

    private fun monitorNotification(): Notification {
        val stop = PendingIntent.getService(this, 1, Intent(this, CrashService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(this, "monitor").setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("CrashGuard is watching for crashes")
            .setContentText(if (prefs.dryRun) "TEST MODE - no real calls or SMS" else "Live mode")
            .addAction(Notification.Action.Builder(null, "Stop", stop).build()).setOngoing(true).build()
    }

    override fun onDestroy() {
        running = false
        handler.removeCallbacksAndMessages(null)
        getSystemService(SensorManager::class.java).unregisterListener(this)
        runCatching { getSystemService(LocationManager::class.java).removeUpdates(this) }
        wake?.takeIf { it.isHeld }?.release()
        super.onDestroy()
    }

    override fun onBind(i: Intent?): IBinder? = null
}
