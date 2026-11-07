package com.crashguard.app

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.telecom.TelecomManager
import android.telephony.SmsManager
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

private const val TAG = "CrashGuard"

object Escalator {
    /** Runs the on-device escalation: SMS contacts -> backend (calls contacts, live link) -> call emergency number. */
    fun run(ctx: Context, p: Prefs, loc: Location?, probability: Double, forceDry: Boolean = false): String? {
        val dry = p.dryRun || forceDry
        val where = loc?.let { "https://maps.google.com/?q=${it.latitude},${it.longitude}" } ?: "location unknown"
        val blood = if (p.bloodGroup.isNotBlank()) " Blood group: ${p.bloodGroup}." else ""
        val text = "EMERGENCY: ${p.userName.ifBlank { "Your contact" }} may have been in a crash.$blood " +
            "Location: $where. Sent automatically by CrashGuard - please call them or ${p.emergencyNumber}."
        if (dry) {
            Log.w(TAG, "DRY RUN escalation: $text | contacts=${p.contacts} | call=${p.callEmergency}")
            return null
        }
        if (granted(ctx, Manifest.permission.SEND_SMS)) {
            for (c in p.contacts) runCatching {
                val sms = if (Build.VERSION.SDK_INT >= 31) ctx.getSystemService(SmsManager::class.java)
                          else @Suppress("DEPRECATION") SmsManager.getDefault()
                sms.sendMultipartTextMessage(c.phone, null, sms.divideMessage(text), null, null)
            }.onFailure { Log.e(TAG, "sms failed", it) }
        }
        var incidentId: String? = null
        if (p.backendUrl.isNotBlank() && p.contacts.isNotEmpty()) {
            val t = thread { incidentId = postIncident(p, loc, probability) }
            t.join(4000)
        }
        if (p.callEmergency && granted(ctx, Manifest.permission.CALL_PHONE)) callEmergency(ctx, p.emergencyNumber)
        return incidentId
    }

    private fun granted(ctx: Context, perm: String) =
        ctx.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED

    private fun callEmergency(ctx: Context, number: String) {
        val uri = Uri.fromParts("tel", number, null)
        runCatching {
            val tm = ctx.getSystemService(TelecomManager::class.java)
            tm.placeCall(uri, Bundle().apply {
                putBoolean(TelecomManager.EXTRA_START_CALL_WITH_SPEAKERPHONE, true)
            })
        }.onFailure {
            runCatching { ctx.startActivity(Intent(Intent.ACTION_CALL, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        }
    }

    private fun http(p: Prefs, path: String, body: JSONObject?): JSONObject? = runCatching {
        val c = URL(p.backendUrl + path).openConnection() as HttpURLConnection
        c.requestMethod = "POST"; c.connectTimeout = 4000; c.readTimeout = 4000
        c.setRequestProperty("content-type", "application/json")
        if (p.apiKey.isNotBlank()) c.setRequestProperty("x-api-key", p.apiKey)
        c.doOutput = true
        c.outputStream.use { it.write((body ?: JSONObject()).toString().toByteArray()) }
        JSONObject(c.inputStream.bufferedReader().readText())
    }.onFailure { Log.e(TAG, "http $path failed", it) }.getOrNull()

    private fun postIncident(p: Prefs, loc: Location?, probability: Double): String? {
        val contacts = JSONArray()
        p.contacts.forEach { contacts.put(JSONObject().put("name", it.name).put("phone", it.phone)) }
        val body = JSONObject()
            .put("user_name", p.userName.ifBlank { "CrashGuard user" })
            .put("lat", loc?.latitude ?: 0.0).put("lon", loc?.longitude ?: 0.0)
            .put("accuracy", loc?.accuracy?.toDouble() ?: 0.0).put("probability", probability)
            .put("contacts", contacts).put("medical", JSONObject().put("blood_group", p.bloodGroup))
        return http(p, "/v1/incidents", body)?.optString("id")
    }

    fun cancelIncident(p: Prefs, id: String?) {
        if (id != null) thread { http(p, "/v1/incidents/$id/cancel", null) }
    }

    fun pushLocation(p: Prefs, id: String?, loc: Location) {
        if (id != null) thread {
            http(p, "/v1/incidents/$id/location",
                JSONObject().put("lat", loc.latitude).put("lon", loc.longitude))
        }
    }
}

/** Every trigger (alerted or not) is stored with its raw window so you can label it and retrain. */
object EventLog {
    fun save(ctx: Context, ev: com.crashguard.core.Evaluation, label: String? = null) {
        val dir = File(ctx.getExternalFilesDir(null), "events").apply { mkdirs() }
        val o = JSONObject()
            .put("t", System.currentTimeMillis()).put("probability", ev.probability)
            .put("positive", ev.positive).put("peak_g", ev.peakG)
            .put("v_pre", ev.vPre).put("v_post", ev.vPost).put("gps_ok", ev.gpsOk)
            .put("label", label ?: JSONObject.NULL)
            .put("acc", JSONArray(ev.acc.map { JSONArray(it.toList()) }))
            .put("gyr", JSONArray(ev.gyr.map { JSONArray(it.toList()) }))
        File(dir, "${System.currentTimeMillis()}.json").writeText(o.toString())
    }

    fun labelLast(ctx: Context, label: String) {
        val f = File(ctx.getExternalFilesDir(null), "events").listFiles()?.maxByOrNull { it.name } ?: return
        runCatching { f.writeText(JSONObject(f.readText()).put("label", label).toString()) }
    }
}
