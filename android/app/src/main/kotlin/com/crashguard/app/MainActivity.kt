package com.crashguard.app

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast

/** Settings + start/stop. Built in code to keep the project dependency-free. */
class MainActivity : Activity() {
    private lateinit var p: Prefs
    private val fields = HashMap<String, EditText>()

    private fun field(root: LinearLayout, key: String, hint: String, value: String, phone: Boolean = false) {
        val e = EditText(this).apply {
            this.hint = hint; setText(value); setSingleLine()
            if (phone) inputType = InputType.TYPE_CLASS_PHONE
        }
        fields[key] = e; root.addView(e)
    }

    private fun label(root: LinearLayout, t: String, size: Float = 16f) =
        root.addView(TextView(this).apply { text = t; textSize = size; setPadding(0, 28, 0, 6) })

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        p = Prefs(this)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(40, 60, 40, 60) }
        label(root, "CrashGuard", 30f)
        label(root, "Automatic crash alerts for you and your people. Starts in TEST MODE: nothing is called or texted until you switch it off.")

        label(root, "You")
        field(root, "name", "Your name", p.userName)
        field(root, "blood", "Blood group (optional, sent to contacts)", p.bloodGroup)
        label(root, "Emergency contacts (with country code, e.g. +91...)")
        val c = p.contacts
        for (i in 0..2) {
            field(root, "cn$i", "Contact ${i + 1} name", c.getOrNull(i)?.name ?: "")
            field(root, "cp$i", "Contact ${i + 1} phone", c.getOrNull(i)?.phone ?: "", true)
        }
        label(root, "Emergency number")
        field(root, "em", "112", p.emergencyNumber, true)
        field(root, "cd", "Countdown seconds (10-120)", p.countdownSec.toString(), true)
        label(root, "Backend (optional: calls contacts in order + live tracking link)")
        field(root, "url", "https://your-server", p.backendUrl)
        field(root, "key", "API key", p.apiKey)

        val dry = CheckBox(this).apply { text = "TEST MODE (no real calls / SMS)"; isChecked = p.dryRun }
        val call = CheckBox(this).apply { text = "Call emergency number automatically"; isChecked = p.callEmergency }
        root.addView(dry); root.addView(call)

        fun save() {
            p.userName = fields["name"]!!.text.toString(); p.bloodGroup = fields["blood"]!!.text.toString()
            p.contacts = (0..2).map { ContactInfo(fields["cn$it"]!!.text.toString(), fields["cp$it"]!!.text.toString()) }
            p.emergencyNumber = fields["em"]!!.text.toString()
            p.countdownSec = fields["cd"]!!.text.toString().toIntOrNull() ?: 30
            p.backendUrl = fields["url"]!!.text.toString(); p.apiKey = fields["key"]!!.text.toString()
            p.dryRun = dry.isChecked; p.callEmergency = call.isChecked
        }

        fun btn(t: String, f: () -> Unit) = root.addView(Button(this).apply { text = t; setOnClickListener { f() } })
        btn("1. Grant permissions") {
            val perms = mutableListOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.SEND_SMS,
                Manifest.permission.CALL_PHONE)
            if (Build.VERSION.SDK_INT >= 33) perms.add(Manifest.permission.POST_NOTIFICATIONS)
            requestPermissions(perms.toTypedArray(), 1)
        }
        btn("2. Save & start monitoring") {
            save()
            startForegroundService(Intent(this, CrashService::class.java))
            Toast.makeText(this, if (p.dryRun) "Monitoring (TEST MODE)" else "Monitoring LIVE", Toast.LENGTH_LONG).show()
        }
        btn("Simulate a crash (always safe: never calls)") {
            save()
            startForegroundService(Intent(this, CrashService::class.java).setAction(CrashService.ACTION_SIMULATE))
        }
        btn("Stop monitoring") { stopService(Intent(this, CrashService::class.java)) }
        label(root, "Every trigger is saved with its raw sensor window in this app's files/events folder, " +
            "labelled when you cancel. Use those to retrain the model (see ml/ in the repo).")
        setContentView(ScrollView(this).apply { addView(root) })
    }
}
