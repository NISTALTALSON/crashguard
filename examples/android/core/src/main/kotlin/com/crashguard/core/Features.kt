package com.crashguard.core

import kotlin.math.abs
import kotlin.math.acos
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Port of ml/features.py. Keep both in sync; ParityTest enforces it. */
object Features {
    const val FS = 50.0
    const val N = 128
    const val COUNT = 21

    private fun norm(a: DoubleArray) = sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])

    private fun countImpacts(mag: DoubleArray, thr: Double = 3.0, minGap: Int = 5): Int {
        var count = 0
        var last = Int.MIN_VALUE / 2
        for (i in 1 until mag.size - 1) {
            if (mag[i] > thr && mag[i] >= mag[i - 1] && mag[i] > mag[i + 1] && i - last >= minGap) {
                count++; last = i
            }
        }
        return count
    }

    private fun unitMean(rows: Array<DoubleArray>, from: Int, to: Int): DoubleArray {
        val m = DoubleArray(3)
        for (i in from until to) for (k in 0..2) m[k] += rows[i][k]
        val n = to - from
        for (k in 0..2) m[k] /= n
        val len = norm(m)
        if (len > 1e-9) for (k in 0..2) m[k] /= len
        return m
    }

    private fun mean(x: DoubleArray, from: Int, to: Int): Double {
        var s = 0.0
        for (i in from until to) s += x[i]
        return s / (to - from)
    }

    private fun std(x: DoubleArray, from: Int, to: Int): Double {
        val m = mean(x, from, to)
        var s = 0.0
        for (i in from until to) s += (x[i] - m) * (x[i] - m)
        return sqrt(s / (to - from))
    }

    /** acc in g (gravity included), gyr in rad/s, both [N][3] at 50 Hz. */
    fun extract(
        acc: Array<DoubleArray>, gyr: Array<DoubleArray>,
        vPre: Double, vPost: Double, gpsOk: Boolean,
    ): DoubleArray {
        require(acc.size == N && gyr.size == N) { "window must be $N samples" }
        val mag = DoubleArray(N) { norm(acc[it]) }
        val gm = DoubleArray(N) { norm(gyr[it]) }
        var pk = 0
        for (i in 1 until N) if (mag[i] > mag[pk]) pk = i
        val peak = mag[pk]
        var jerk = 0.0
        for (i in 1 until N) jerk = max(jerk, abs(mag[i] - mag[i - 1]))
        jerk *= FS
        var energy = 0.0
        for (m in mag) energy += max(m - 2.0, 0.0)
        energy /= FS
        val preFrom = max(0, pk - 25)
        var freefall = 0.0
        if (pk > preFrom) {
            var c = 0
            for (i in preFrom until pk) if (mag[i] < 0.5) c++
            freefall = c.toDouble() / (pk - preFrom)
        }
        val widthMs = mag.count { it > 0.5 * peak } * 1000.0 / FS
        val above3Ms = mag.count { it > 3.0 } * 1000.0 / FS
        val gyroPost = mean(gm, min(N - 1, pk + 5), N)
        var near = 0.0
        for (i in max(0, pk - 15) until min(N, pk + 16)) near = max(near, gm[i])
        val g0 = unitMean(acc, 0, 15)
        val g1 = unitMean(acc, N - 15, N)
        val cos = (g0[0] * g1[0] + g0[1] * g1[1] + g0[2] * g1[2]).coerceIn(-1.0, 1.0)
        val orient = Math.toDegrees(acos(cos))
        val postStd = std(mag, N - 40, N)
        val postDev = abs(mean(mag, N - 40, N) - 1.0)
        val preStd = std(mag, 0, 20)
        val above2Ms = mag.count { it > 2.0 } * 1000.0 / FS
        var still = 0
        for (i in N - 40 until N) if (abs(mag[i] - 1.0) < 0.08) still++
        val stillFrac = still / 40.0
        val vp: Double; val vq: Double; val drop: Double; val ratio: Double
        if (gpsOk) {
            vp = vPre; vq = vPost; drop = vp - vq; ratio = vq / max(vp, 0.5)
        } else {
            vp = 0.0; vq = 0.0; drop = 0.0; ratio = 0.0
        }
        return doubleArrayOf(
            ln(1.0 + peak), ln(1.0 + jerk), ln(1.0 + energy), freefall,
            countImpacts(mag).toDouble(), widthMs, above3Ms, gm.max(), gyroPost,
            near, orient, postStd, postDev, preStd,
            vp, vq, drop, ratio, if (gpsOk) 1.0 else 0.0,
            above2Ms, stillFrac,
        )
    }
}
