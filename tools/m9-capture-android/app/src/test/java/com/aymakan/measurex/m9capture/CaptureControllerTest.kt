package com.aymakan.measurex.m9capture

import kotlin.math.cos
import kotlin.math.sin
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.junit.Test

/** Candidate eligibility, azimuth coverage and completion logic (GT-free). */
class CaptureControllerTest {

    private val target = doubleArrayOf(0.0, 0.0, 0.0)

    /** A camera centre 1.5 m from target at azimuth [deg] in the horizontal plane. */
    private fun cam(deg: Double): DoubleArray {
        val r = Math.toRadians(deg)
        // horizontalBasis(up=+Y) => a=+X, b=+Z, so azimuth is measured in the XZ plane.
        return doubleArrayOf(1.5 * cos(r), 0.0, 1.5 * sin(r))
    }

    @Test
    fun coverageIsContiguousArcNotFullCircle() {
        val arc = (0..120 step 15).map { it.toDouble() }
        assertEquals(120.0, CaptureController.coverageDeg(arc), 1.0)
    }

    @Test
    fun firstCandidateAlwaysAccepted() {
        val c = CaptureController(target)
        assertTrue(c.shouldAccept(cam(0.0)))
    }

    @Test
    fun rejectsNearDuplicateViewpoint() {
        val c = CaptureController(target, minAngularSeparationDeg = 8.0)
        c.accept(cam(0.0))
        assertFalse(c.shouldAccept(cam(3.0)))  // only 3 deg apart
        assertTrue(c.shouldAccept(cam(10.0)))  // 10 deg apart
    }

    @Test
    fun completesAtTwelveCandidatesAcrossTargetCoverage() {
        val c = CaptureController(target, minAngularSeparationDeg = 8.0)
        // -65 .. +65 deg in ~10 deg steps => 14 candidates spanning ~130 deg.
        var deg = -65.0
        while (deg <= 70.0) {
            if (c.shouldAccept(cam(deg))) c.accept(cam(deg))
            deg += 10.0
        }
        assertTrue(c.count >= 12, "count=${c.count}")
        assertTrue(c.coverageDeg() >= c.targetCoverageDeg, "coverage=${c.coverageDeg()}")
        assertTrue(c.isComplete())
        assertTrue(c.totalBaselineM() > 0.0)
    }

    @Test
    fun incompleteAt120ButCompleteAt125() {
        // On-device completion needs targetCoverageDeg (125), not the offline 120 min.
        fun sweep(maxDeg: Double): CaptureController {
            val c = CaptureController(target, minAngularSeparationDeg = 8.0)
            var deg = 0.0
            while (deg <= maxDeg) {
                if (c.shouldAccept(cam(deg))) c.accept(cam(deg))
                deg += 10.0
            }
            return c
        }
        val at120 = sweep(120.0)  // 13 candidates, exactly 120 deg coverage
        assertTrue(at120.count >= 12, "count=${at120.count}")
        assertEquals(120.0, at120.coverageDeg(), 1.0)
        assertFalse(at120.isComplete(), "120 deg must not satisfy the 125 deg target")
        assertTrue(sweep(130.0).isComplete())
    }

    @Test
    fun removedFailedFrameDropsFromCoverageAndCount() {
        val c = CaptureController(target, minAngularSeparationDeg = 8.0)
        c.accept(cam(0.0), "000001")
        c.accept(cam(40.0), "000002")
        c.accept(cam(80.0), "000003")
        assertEquals(3, c.count)
        c.remove("000002")
        assertEquals(2, c.count)
        // A near-duplicate of the removed viewpoint is accepted again (lastAzimuth rolled
        // back to the surviving tail, 80 deg), so capture can replace the lost frame.
        assertTrue(c.shouldAccept(cam(40.0)))
    }

    @Test
    fun incompleteWhenCoverageTooNarrow() {
        val c = CaptureController(target, minAngularSeparationDeg = 8.0)
        // Many frames but only across ~50 deg — not enough coverage.
        for (deg in listOf(0.0, 10.0, 20.0, 30.0, 40.0, 50.0)) {
            if (c.shouldAccept(cam(deg))) c.accept(cam(deg))
        }
        assertFalse(c.isComplete())
    }

    @Test
    fun angularDistanceWrapsAround() {
        assertEquals(20.0, CaptureController.angularDistanceDeg(350.0, 10.0), 1e-9)
        assertEquals(170.0, CaptureController.angularDistanceDeg(-90.0, 80.0), 1e-9)
    }
}
