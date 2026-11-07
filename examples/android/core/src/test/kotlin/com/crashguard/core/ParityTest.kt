package com.crashguard.core

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ParityTest {
    private fun read(prop: String) = File(System.getProperty(prop)).readText()

    private fun matrix(a: JSONArray) = Array(a.length()) { i ->
        val r = a.getJSONArray(i); DoubleArray(r.length()) { r.getDouble(it) }
    }

    @Test
    fun kotlinFeaturesAndModelMatchPython() {
        val model = Model.fromJson(read("model.path"))
        val cases = JSONArray(read("parity.path"))
        assertTrue(cases.length() > 0)
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val f = Features.extract(
                matrix(c.getJSONArray("acc")), matrix(c.getJSONArray("gyr")),
                c.getDouble("v_pre"), c.getDouble("v_post"), c.getInt("gps_ok") == 1,
            )
            val expected = c.getJSONArray("features")
            assertEquals(Features.COUNT, expected.length())
            for (k in 0 until Features.COUNT) {
                val e = expected.getDouble(k)
                assertEquals("${c.getString("name")} feature $k", e, f[k], 1e-3 + 1e-3 * Math.abs(e))
            }
            assertEquals(c.getString("name"), c.getDouble("probability"), model.predict(f), 1e-3)
        }
    }

    @Test
    fun detectorTriggersOnceAndEvaluates() {
        val model = Model.fromJson(read("model.path"))
        val results = ArrayList<Evaluation>()
        val d = CrashDetector(model) { results.add(it) }
        var t = 1_000_000_000L
        val g = 9.80665
        fun feed(n: Int, mag: Double) {
            repeat(n) { d.onGyroscope(0.0, 0.0, 0.0); d.onAccelerometer(t, 0.0, 0.0, mag * g); t += 20_000_000L }
        }
        d.onSpeed(t - 2_000_000_000L, 12.0)
        feed(100, 1.0)          // normal driving
        feed(3, 9.0)            // impact
        feed(300, 1.0)          // 6 s of stillness
        d.onSpeed(t - 2_000_000_000L, 0.0)
        feed(30, 1.0)
        d.tick(t)
        assertEquals(1, results.size)
        assertTrue(results[0].peakG >= 8.9)
        assertTrue(results[0].probability in 0.0..1.0)
    }
}
