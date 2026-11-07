package com.crashguard.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class ContactInfo(val name: String, val phone: String)

/** All settings live in SharedPreferences. dryRun defaults to TRUE: no real calls/SMS until you turn it off. */
class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("crashguard", Context.MODE_PRIVATE)

    var userName: String
        get() = sp.getString("userName", "") ?: ""
        set(v) = sp.edit().putString("userName", v).apply()
    var bloodGroup: String
        get() = sp.getString("blood", "") ?: ""
        set(v) = sp.edit().putString("blood", v).apply()
    var backendUrl: String
        get() = sp.getString("backend", "") ?: ""
        set(v) = sp.edit().putString("backend", v.trim().trimEnd('/')).apply()
    var apiKey: String
        get() = sp.getString("apiKey", "") ?: ""
        set(v) = sp.edit().putString("apiKey", v).apply()
    var emergencyNumber: String
        get() = sp.getString("emergency", "112") ?: "112"
        set(v) = sp.edit().putString("emergency", v.trim().ifEmpty { "112" }).apply()
    var dryRun: Boolean
        get() = sp.getBoolean("dryRun", true)
        set(v) = sp.edit().putBoolean("dryRun", v).apply()
    var callEmergency: Boolean
        get() = sp.getBoolean("callEmergency", true)
        set(v) = sp.edit().putBoolean("callEmergency", v).apply()
    var countdownSec: Int
        get() = sp.getInt("countdown", 30)
        set(v) = sp.edit().putInt("countdown", v.coerceIn(10, 120)).apply()

    var contacts: List<ContactInfo>
        get() {
            val a = JSONArray(sp.getString("contacts", "[]"))
            return (0 until a.length()).map {
                val o = a.getJSONObject(it); ContactInfo(o.getString("name"), o.getString("phone"))
            }
        }
        set(v) {
            val a = JSONArray()
            v.filter { it.phone.isNotBlank() }.forEach {
                a.put(JSONObject().put("name", it.name.ifBlank { it.phone }).put("phone", it.phone.trim()))
            }
            sp.edit().putString("contacts", a.toString()).apply()
        }
}
