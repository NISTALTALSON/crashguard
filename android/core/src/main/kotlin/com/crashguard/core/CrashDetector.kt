package com.crashguard.core

import kotlin.math.sqrt

class Sample(val tNs: Long, val acc: DoubleArray, val gyr: DoubleArray)

class Evaluation(
    val probability: Double, val positive: Boolean, val features: DoubleArray,
    val acc: Array<DoubleArray>, val gyr: Array<DoubleArray>,
    val vPre: Double, val vPost: Double, val gpsOk: Boolean,
    val peakG: Double, val triggerTNs: Long,
)

/** Peak-hold decimation of raw high-rate sensor data to 50 Hz (matches the training simulator). */
class Decimator(private val emit: (Sample) -> Unit) {
    private val binNs = 20_000_000L
    private var bin = Long.MIN_VALUE
    private var best: DoubleArray? = null
    private var bestG: DoubleArray = DoubleArray(3)
    private var bestMag = -1.0
    private var bestT = 0L
    private var gyro = DoubleArray(3)

    fun onGyro(x: Double, y: Double, z: Double) { gyro = doubleArrayOf(x, y, z) }

    fun onAccel(tNs: Long, axG: Double, ayG: Double, azG: Double) {
        val b = tNs / binNs
        if (b != bin) { flush(); bin = b; bestMag = -1.0; best = null }
        val m = sqrt(axG * axG + ayG * ayG + azG * azG)
        if (m > bestMag) { bestMag = m; best = doubleArrayOf(axG, ayG, azG); bestG = gyro; bestT = tNs }
    }

    private fun flush() { best?.let { emit(Sample(bestT, it, bestG)) } }
}

/**
 * Stage 1  trigger: 50 Hz |a| >= model.triggerG
 * Stage 2  collect 2.56 s window (impact at sample 40) + wait for GPS speed to settle (5 s)
 * Stage 3  MLP decides; positive -> ALERTING until reset() (caller runs countdown / escalation)
 * Pure Kotlin, no Android deps: runs on phone, watch and in JVM unit tests.
 */
class CrashDetector(
    private val model: Model,
    private val onEvaluated: (Evaluation) -> Unit,
) {
    enum class State { MONITORING, COLLECTING, ALERTING }

    var state = State.MONITORING
        private set

    private val g = 9.80665
    private val sec = 1_000_000_000L
    private val buf = ArrayList<Sample>()
    private var seqBase = 0L
    private var trigSeq = -1L
    private var trigT = 0L
    private var cooldownUntil = 0L
    private var frozen: Pair<Array<DoubleArray>, Array<DoubleArray>>? = null
    private val speeds = ArrayList<Pair<Long, Double>>()
    private val dec = Decimator(::onSample)

    fun onAccelerometer(tNs: Long, axMs2: Double, ayMs2: Double, azMs2: Double) =
        dec.onAccel(tNs, axMs2 / g, ayMs2 / g, azMs2 / g)

    fun onGyroscope(x: Double, y: Double, z: Double) = dec.onGyro(x, y, z)

    fun onSpeed(tNs: Long, mps: Double) {
        speeds.add(tNs to mps)
        while (speeds.size > 40) speeds.removeAt(0)
    }

    fun reset(nowNs: Long) {
        state = State.MONITORING; trigSeq = -1; frozen = null; cooldownUntil = nowNs + 3 * sec
    }

    /** Call periodically (e.g. 1 Hz) so evaluation still happens if sensor delivery stalls. */
    fun tick(nowNs: Long) { maybeEvaluate(nowNs) }

    private fun onSample(s: Sample) {
        buf.add(s)
        if (buf.size > 600) { buf.subList(0, 200).clear(); seqBase += 200 }
        val seq = seqBase + buf.size - 1
        val mag = sqrt(s.acc[0] * s.acc[0] + s.acc[1] * s.acc[1] + s.acc[2] * s.acc[2])
        if (state == State.MONITORING && mag >= model.triggerG && s.tNs >= cooldownUntil) {
            state = State.COLLECTING; trigSeq = seq; trigT = s.tNs; frozen = null
        }
        if (state == State.COLLECTING && frozen == null && seq >= trigSeq + 87) freeze()
        maybeEvaluate(s.tNs)
    }

    private fun freeze() {
        val acc = Array(Features.N) { DoubleArray(3) }
        val gyr = Array(Features.N) { DoubleArray(3) }
        for (k in 0 until Features.N) {
            val idx = (trigSeq - 40 + k - seqBase).toInt().coerceIn(0, buf.size - 1)
            acc[k] = buf[idx].acc.copyOf(); gyr[k] = buf[idx].gyr.copyOf()
        }
        frozen = acc to gyr
    }

    private fun meanSpeed(from: Long, to: Long): Double? {
        val v = speeds.filter { it.first in from..to }.map { it.second }
        return if (v.isEmpty()) null else v.average()
    }

    private fun maybeEvaluate(now: Long) {
        if (state != State.COLLECTING || now < trigT + 5 * sec) return
        if (frozen == null) freeze()
        val (acc, gyr) = frozen!!
        val vp = meanSpeed(trigT - 6 * sec, trigT - sec / 3)
        val vq = meanSpeed(trigT + 3 * sec, trigT + 5 * sec + sec / 5)
        val gpsOk = vp != null && vq != null
        val f = Features.extract(acc, gyr, vp ?: 0.0, vq ?: 0.0, gpsOk)
        val p = model.predict(f)
        val positive = p >= model.threshold
        var peak = 0.0
        for (a in acc) peak = maxOf(peak, sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]))
        if (positive) state = State.ALERTING else reset(now)
        trigSeq = -1; frozen = null
        onEvaluated(Evaluation(p, positive, f, acc, gyr, vp ?: 0.0, vq ?: 0.0, gpsOk, peak, trigT))
    }
}
