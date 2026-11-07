package com.crashguard.wear

import android.Manifest
import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Bundle
import android.os.CountDownTimer
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.crashguard.core.CrashDetector
import com.crashguard.core.Model
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.WearableListenerService

fun sendToPhone(ctx: Context, path: String, payload: String) =
    Wearable.getNodeClient(ctx).connectedNodes.addOnSuccessListener { nodes ->
        nodes.forEach { Wearable.getMessageClient(ctx).sendMessage(it.id, path, payload.toByteArray()) }
    }

/** Runs the same detector as the phone, on the wrist. GPS speed is unavailable here -> gps_ok = 0 path of the model. */
class WearMonitorService : Service(), SensorEventListener {
    private lateinit var detector: CrashDetector
    private var wake: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("mon", "Monitoring", NotificationManager.IMPORTANCE_LOW))
        val n = Notification.Builder(this, "mon").setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("CrashGuard watching").setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH)
        else startForeground(1, n)
        val model = Model.fromJson(assets.open("crash_model.json").bufferedReader().readText())
        detector = CrashDetector(model) { ev ->
            if (ev.positive) {
                sendToPhone(this, "/crashguard/suspected", ev.probability.toString())
                startActivity(Intent(this, Countdown::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            } else detector.reset(SystemClock.elapsedRealtimeNanos())
        }
        val sm = getSystemService(SensorManager::class.java)
        sm.registerListener(this, sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER), 5000)
        sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.let { sm.registerListener(this, it, 5000) }
        wake = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "crashguard:watch").apply { acquire() }
    }

    override fun onStartCommand(i: Intent?, f: Int, s: Int): Int {
        if (i?.action == "reset") detector.reset(SystemClock.elapsedRealtimeNanos())
        detector.tick(SystemClock.elapsedRealtimeNanos())
        return START_STICKY
    }

    override fun onSensorChanged(e: SensorEvent) {
        if (e.sensor.type == Sensor.TYPE_ACCELEROMETER)
            detector.onAccelerometer(e.timestamp, e.values[0].toDouble(), e.values[1].toDouble(), e.values[2].toDouble())
        else detector.onGyroscope(e.values[0].toDouble(), e.values[1].toDouble(), e.values[2].toDouble())
        if (e.timestamp % 50 == 0L) detector.tick(SystemClock.elapsedRealtimeNanos())
    }

    override fun onAccuracyChanged(s: Sensor?, a: Int) {}
    override fun onBind(i: Intent?): IBinder? = null
    override fun onDestroy() {
        getSystemService(SensorManager::class.java).unregisterListener(this)
        wake?.takeIf { it.isHeld }?.release(); super.onDestroy()
    }
}

class WearMain : Activity() {
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        requestPermissions(arrayOf(Manifest.permission.BODY_SENSORS, Manifest.permission.POST_NOTIFICATIONS), 1)
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            addView(Button(this@WearMain).apply { text = "Start"; setOnClickListener {
                startForegroundService(Intent(this@WearMain, WearMonitorService::class.java)) } })
            addView(Button(this@WearMain).apply { text = "Stop"; setOnClickListener {
                stopService(Intent(this@WearMain, WearMonitorService::class.java)) } })
        })
    }
}

/** Shown on the wrist during the countdown: haptics + one big cancel button. */
class Countdown : Activity() {
    private var timer: CountDownTimer? = null
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        val secs = intent.getIntExtra("secs", 30)
        val t = TextView(this).apply { textSize = 40f; gravity = Gravity.CENTER; setTextColor(Color.WHITE) }
        val cancel = Button(this).apply { text = "I'M OK"; setOnClickListener {
            sendToPhone(this@Countdown, "/crashguard/cancel", ""); finish() } }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setBackgroundColor(Color.parseColor("#B71C1C"))
            addView(t); addView(cancel)
        })
        val v = getSystemService(Vibrator::class.java)
        timer = object : CountDownTimer(secs * 1000L, 1000) {
            override fun onTick(ms: Long) {
                t.text = (ms / 1000).toString()
                v.vibrate(VibrationEffect.createOneShot(500, 255))
            }
            override fun onFinish() { t.text = "SENT" }
        }.start()
    }

    override fun onDestroy() {
        timer?.cancel()
        startService(Intent(this, WearMonitorService::class.java).setAction("reset"))
        super.onDestroy()
    }
}

class WatchListener : WearableListenerService() {
    override fun onMessageReceived(e: MessageEvent) {
        when (e.path) {
            "/crashguard/countdown" -> startActivity(Intent(this, Countdown::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK).putExtra("secs", String(e.data).toIntOrNull() ?: 30))
        }
    }
}
