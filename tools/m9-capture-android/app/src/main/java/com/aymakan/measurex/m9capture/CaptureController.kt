package com.aymakan.measurex.m9capture

import kotlin.math.abs

/**
 * GT-free capture-session state: decides when a tracked camera observation is a new
 * *candidate* frame (enough angular separation from the last one), tracks azimuth
 * coverage around the target, and reports completion. Pure Kotlin so the
 * angle/coverage/eligibility logic is unit-tested without a device.
 *
 * The app over-collects candidates (12–20) across ≥120° of view coverage; exactly 8
 * are chosen later, offline. Nothing here imposes carton dimensions, and no
 * dimension is ever estimated.
 */
class CaptureController(
    private val target: DoubleArray,
    private val gravityWorld: DoubleArray = PoseConvention.GRAVITY_WORLD,
    private val minAngularSeparationDeg: Double = 8.0,
    val minCandidates: Int = 12,
    val minCoverageDeg: Double = 120.0,
    val targetCoverageDeg: Double = 125.0,
) {
    data class Candidate(
        val cameraCenter: DoubleArray,
        val azimuthDeg: Double,
        val baselineFromPrevM: Double,
        val frameId: String = "",
    )

    private val candidates = mutableListOf<Candidate>()
    private var lastAzimuth: Double? = null

    val count: Int get() = candidates.size
    val azimuths: List<Double> get() = candidates.map { it.azimuthDeg }

    /** Angular separation (deg) of [cameraCenter]'s azimuth from the last candidate's. */
    fun separationFromLast(cameraCenter: DoubleArray): Double {
        val last = lastAzimuth ?: return Double.POSITIVE_INFINITY
        val az = PoseConvention.azimuthDeg(cameraCenter, target, gravityWorld)
        return angularDistanceDeg(az, last)
    }

    /**
     * True when a TRACKING observation at [cameraCenter] is far enough from the last
     * accepted candidate to be worth saving. The caller gates tracking state and
     * image availability separately.
     */
    fun shouldAccept(cameraCenter: DoubleArray): Boolean =
        separationFromLast(cameraCenter) >= minAngularSeparationDeg

    /** Record a candidate; returns its azimuth. The caller has already decided to save. */
    fun accept(cameraCenter: DoubleArray, frameId: String = ""): Double {
        val az = PoseConvention.azimuthDeg(cameraCenter, target, gravityWorld)
        val baseline = candidates.lastOrNull()?.let { distance(it.cameraCenter, cameraCenter) } ?: 0.0
        candidates.add(Candidate(cameraCenter.copyOf(), az, baseline, frameId))
        lastAzimuth = az
        return az
    }

    /**
     * Drop the candidate for [frameId] — used when its JPEG write failed, so a failed
     * frame never counts toward coverage/completion and can be replaced by a later
     * viewpoint. `lastAzimuth` is restored to the surviving tail so separation gating
     * stays correct.
     */
    fun remove(frameId: String) {
        if (candidates.removeAll { it.frameId == frameId }) {
            lastAzimuth = candidates.lastOrNull()?.azimuthDeg
        }
    }

    /** Total camera travel across candidates (metres). */
    fun totalBaselineM(): Double = candidates.sumOf { it.baselineFromPrevM }

    /** View coverage: the contiguous arc the candidates span (`360 - largest gap`). */
    fun coverageDeg(): Double = coverageDeg(azimuths)

    /**
     * On-device completion. Requires [minCandidates] frames across [targetCoverageDeg]
     * — a small margin above the offline research minimum ([minCoverageDeg], still the
     * only gate the offline validator enforces) so frame selection has slack.
     */
    fun isComplete(): Boolean = count >= minCandidates && coverageDeg() >= targetCoverageDeg

    companion object {
        /** Angular extent spanned by azimuths on the circle: `360 - largest gap`. */
        fun coverageDeg(azimuths: List<Double>): Double {
            if (azimuths.size < 2) return 0.0
            val s = azimuths.map { ((it % 360.0) + 360.0) % 360.0 }.sorted()
            var maxGap = 360.0 - s.last() + s.first()  // wrap-around gap
            for (i in 0 until s.size - 1) maxGap = maxOf(maxGap, s[i + 1] - s[i])
            return 360.0 - maxGap
        }

        /** Shortest angular distance (deg) between two azimuths, in [0, 180]. */
        fun angularDistanceDeg(a: Double, b: Double): Double {
            var d = abs(a - b) % 360.0
            if (d > 180.0) d = 360.0 - d
            return d
        }

        private fun distance(a: DoubleArray, b: DoubleArray): Double {
            val dx = a[0] - b[0]; val dy = a[1] - b[1]; val dz = a[2] - b[2]
            return kotlin.math.sqrt(dx * dx + dy * dy + dz * dz)
        }
    }
}
