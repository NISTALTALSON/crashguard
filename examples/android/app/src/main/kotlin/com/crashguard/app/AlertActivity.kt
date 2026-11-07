package com.crashguard.app

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Full-screen countdown. One giant button: I'M OK. */
class AlertActivity : Activity() {
    private lateinit var big: TextView
    private lateinit var sub: TextView

    private val rx = object : BroadcastReceiver() {
        override fun onReceive(c: Context, i: Intent) {
            when (i.getStringExtra(CrashService.EXTRA_PHASE)) {
                "counting" -> big.text = i.getIntExtra(CrashService.EXTRA_REMAINING, 0).toString()
                "sent" -> { big.text = "SENT"; sub.text = "Emergency contacts have been alerted. Help is on the way." }
                "cancelled" -> finish()
            }
        }
    }

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        if (Build.VERSION.SDK_INT >= 27) { setShowWhenLocked(true); setTurnScreenOn(true) }
        else @Suppress("DEPRECATION") window.addFlags(
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            setBackgroundColor(Color.parseColor("#B71C1C")); setPadding(48, 48, 48, 48)
        }
        root.addView(TextView(this).apply {
            text = "CRASH DETECTED"; textSize = 28f; setTextColor(Color.WHITE); gravity = Gravity.CENTER })
        big = TextView(this).apply { text = "..."; textSize = 120f; setTextColor(Color.WHITE); gravity = Gravity.CENTER }
        root.addView(big)
        sub = TextView(this).apply {
            text = "Calling emergency contacts and ${Prefs(this@AlertActivity).emergencyNumber} when this reaches 0"
            textSize = 18f; setTextColor(Color.WHITE); gravity = Gravity.CENTER }
        root.addView(sub)
        root.addView(Button(this).apply {
            text = "I'M OK - CANCEL"; textSize = 26f
            setOnClickListener {
                startService(Intent(this@AlertActivity, CrashService::class.java).setAction(CrashService.ACTION_CANCEL))
                finish()
            }
        }, LinearLayout.LayoutParams(-1, 300).apply { topMargin = 64 })
        setContentView(root)
    }

    override fun onStart() {
        super.onStart()
        val f = IntentFilter(CrashService.ACTION_TICK)
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(rx, f, Context.RECEIVER_NOT_EXPORTED) else registerReceiver(rx, f)
    }

    override fun onStop() { unregisterReceiver(rx); super.onStop() }
}
