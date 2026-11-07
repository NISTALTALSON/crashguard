package com.crashguard.core

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.exp
import kotlin.math.max

/** MLP exported by ml/train.py (JSON): standardise -> relu layers -> sigmoid. */
class Model(
    val triggerG: Double,
    val threshold: Double,
    private val mean: DoubleArray,
    private val std: DoubleArray,
    private val weights: List<Array<DoubleArray>>,   // [layer][in][out]
    private val biases: List<DoubleArray>,
) {
    fun predict(x: DoubleArray): Double {
        require(x.size == mean.size) { "expected ${mean.size} features, got ${x.size}" }
        var h = DoubleArray(x.size) { (x[it] - mean[it]) / std[it] }
        for (l in weights.indices) {
            val w = weights[l]; val b = biases[l]
            val out = DoubleArray(b.size) { j ->
                var s = b[j]
                for (i in h.indices) s += h[i] * w[i][j]
                s
            }
            h = if (l < weights.size - 1) DoubleArray(out.size) { max(out[it], 0.0) } else out
        }
        return 1.0 / (1.0 + exp(-h[0]))
    }

    companion object {
        private fun vec(a: JSONArray) = DoubleArray(a.length()) { a.getDouble(it) }

        fun fromJson(text: String): Model {
            val o = JSONObject(text)
            val w = o.getJSONArray("weights")
            val b = o.getJSONArray("biases")
            val weights = (0 until w.length()).map { l ->
                val m = w.getJSONArray(l)
                Array(m.length()) { vec(m.getJSONArray(it)) }
            }
            val biases = (0 until b.length()).map { vec(b.getJSONArray(it)) }
            return Model(o.getDouble("trigger_g"), o.getDouble("threshold"),
                vec(o.getJSONArray("mean")), vec(o.getJSONArray("std")), weights, biases)
        }
    }
}
