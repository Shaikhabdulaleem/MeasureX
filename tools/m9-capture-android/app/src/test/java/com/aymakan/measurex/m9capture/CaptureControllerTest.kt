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
    fun completesAtTwelveCandidatesAcrossCoverage() {
        val c = CaptureController(target, minAngularSeparationDeg = 8.0)
        // -60 .. +65 deg in ~10 deg steps => 13 candidates spanning ~125 deg.
        var deg = -60.0
        while (deg <= 65.0) {
            if (c.shouldAccept(cam(deg))) c.accept(cam(deg))
            deg += 10.0
        }
        assertTrue(c.count >= 12, "count=${c.count}")
        assertTrue(c.coverageDeg() >= 120.0, "coverage=${c.coverageDeg()}")
        assertTrue(c.isComplete())
        assertTrue(c.totalBaselineM() > 0.0)
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
