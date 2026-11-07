package com.crashguard.app

import android.content.Intent
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService

/** Messages coming from the watch: cancel button pressed, or the watch itself detected a crash. */
class PhoneWearListener : WearableListenerService() {
    override fun onMessageReceived(e: MessageEvent) {
        val action = when (e.path) {
            "/crashguard/cancel" -> CrashService.ACTION_CANCEL
            "/crashguard/suspected" -> CrashService.ACTION_WATCH_ALERT
            else -> return
        }
        startForegroundService(Intent(this, CrashService::class.java).setAction(action)
            .putExtra("p", String(e.data).toDoubleOrNull() ?: 0.9))
    }
}
