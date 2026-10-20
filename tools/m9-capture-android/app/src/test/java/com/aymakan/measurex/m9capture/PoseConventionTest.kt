package com.aymakan.measurex.m9capture

import kotlin.math.cos
import kotlin.math.sin
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.Test

/**
 * MANDATORY coordinate-convention tests. A bug in the ARCore → M9 conversion would
 * silently invalidate every real measurement, so these are deterministic and
 * exact. See [PoseConvention].
 */
class PoseConventionTest {

    private val eps = 1e-9

    /**
     * The mandatory front-of-camera check. A point one metre visually in front of
     * the ARCore camera has ARCore camera coordinates `[0, 0, -1]` (ARCore forward is
     * `-Z`). Converted to the M9 camera frame it must be `[0, 0, +1]` (OpenCV forward
     * is `+Z`), i.e. depth `+1 > 0`, and it must project at the principal point.
     */
    @Test
    fun frontPointConvertsToPositiveDepthAtPrincipalPoint() {
        // C is involutory (diag(1,-1,-1) squared = I), so it maps ARCore-cam -> M9-cam too.
        val m9 = PoseConvention.C_ARCORE_FROM_M9.transform(0.0, 0.0, -1.0, 0.0)
        assertEquals(0.0, m9[0], eps)
        assertEquals(0.0, m9[1], eps)
        assertEquals(1.0, m9[2], eps)   // depth > 0
        assertTrue(m9[2] > 0.0)

        // Projection with K puts it at the principal point.
        val fx = 1000.0; val fy = 1000.0; val cx = 320.0; val cy = 240.0
        val z = m9[2]
        val u = cx + fx * m9[0] / z
        val v = cy + fy * m9[1] / z
        assertEquals(cx, u, 1e-6)
        assertEquals(cy, v, 1e-6)
    }

    @Test
    fun conversionRotationDeterminantIsPlusOne() {
        assertEquals(1.0, PoseConvention.C_ARCORE_FROM_M9.rotationDeterminant(), eps)
    }

    @Test
    fun invertRigidIsAProperInverse() {
        // A non-trivial ARCore pose: 30 deg about Y, translated.
        val t = arcorePose(yawDeg = 30.0, tx = 0.2, ty = -0.1, tz = 1.5)
        val m9 = PoseConvention.arcoreToM9Pose(t)
        val product = m9.invertRigid() * m9
        val id = Mat4.identity()
        for (i in 0 until 4) for (j in 0 until 4) {
            assertEquals(id[i, j], product[i, j], 1e-9)
        }
        assertEquals(1.0, m9.rotationDeterminant(), 1e-9)
    }

    @Test
    fun conversionPreservesCameraCentre() {
        val t = arcorePose(yawDeg = 45.0, tx = 0.3, ty = 0.4, tz = 2.0)
        val m9 = PoseConvention.arcoreToM9Pose(t)
        // Right-multiplying by C (no translation) leaves the translation column intact.
        assertEquals(0.3, m9.translation()[0], eps)
        assertEquals(0.4, m9.translation()[1], eps)
        assertEquals(2.0, m9.translation()[2], eps)
    }

    @Test
    fun m9ForwardEqualsArcoreForwardInWorld() {
        // ARCore camera forward is -Z (its column 2 negated); the M9 camera +Z axis in
        // world must point the same way the ARCore camera looks.
        val t = arcorePose(yawDeg = 20.0, tx = 0.0, ty = 0.0, tz = 1.0)
        val m9 = PoseConvention.arcoreToM9Pose(t)
        val arcoreForward = doubleArrayOf(-t[0, 2], -t[1, 2], -t[2, 2])  // -Z column
        for (i in 0 until 3) assertEquals(arcoreForward[i], m9[i, 2], 1e-9)
    }

    @Test
    fun columnMajorIsDeColumnMajoredNotTransposed() {
        // Build a row-major matrix, store it column-major (as Pose.toMatrix would),
        // then read it back — must recover the original, not its transpose.
        val rowMajor = doubleArrayOf(
            1.0, 2.0, 3.0, 4.0,
            5.0, 6.0, 7.0, 8.0,
            9.0, 10.0, 11.0, 12.0,
            13.0, 14.0, 15.0, 16.0,
        )
        val columnMajor = FloatArray(16)
        for (row in 0 until 4) for (col in 0 until 4) {
            columnMajor[col * 4 + row] = rowMajor[row * 4 + col].toFloat()
        }
        val m = Mat4.fromColumnMajor(columnMajor)
        for (i in 0 until 4) for (j in 0 until 4) {
            assertEquals(rowMajor[i * 4 + j], m[i, j], 1e-6)
        }
    }

    @Test
    fun gravityUpIsPlusY() {
        val up = PoseConvention.upFromGravity()  // gravity = [0,-1,0]
        assertEquals(0.0, up[0], eps)
        assertEquals(1.0, up[1], eps)
        assertEquals(0.0, up[2], eps)
    }

    @Test
    fun supportPlaneNormalIsUnitAndGravityUp() {
        // A horizontal floor through y = -0.5, normal supplied pointing down (-Y) —
        // must be canonicalised to unit length and oriented gravity-up (+Y).
        val plane = PoseConvention.supportPlane(
            pointOnPlane = doubleArrayOf(1.0, -0.5, 2.0),
            planeNormalWorld = doubleArrayOf(0.0, -3.0, 0.0),
        )
        val n = plane.normal
        assertEquals(0.0, n[0], eps)
        assertEquals(1.0, n[1], eps)   // flipped to +Y, unit length
        assertEquals(0.0, n[2], eps)
        // offset = -n·P = -(1 * -0.5) = 0.5  => n·X + offset = 0 holds on the plane.
        assertEquals(0.5, plane.offset, eps)
        assertEquals(0.0, n[1] * (-0.5) + plane.offset, eps)
    }

    @Test
    fun azimuthSpansWithViewpoint() {
        val target = doubleArrayOf(0.0, 0.0, 0.0)
        // Two camera centres 90 deg apart in the horizontal (XZ) plane around target.
        val a = PoseConvention.azimuthDeg(doubleArrayOf(2.0, 0.0, 0.0), target)
        val b = PoseConvention.azimuthDeg(doubleArrayOf(0.0, 0.0, 2.0), target)
        assertEquals(90.0, CaptureController.angularDistanceDeg(a, b), 1e-6)
    }

    /** `T_world_from_camera` for an ARCore camera rotated [yawDeg] about world Y. */
    private fun arcorePose(yawDeg: Double, tx: Double, ty: Double, tz: Double): Mat4 {
        val r = Math.toRadians(yawDeg)
        val c = cos(r); val s = sin(r)
        val m = doubleArrayOf(
            c, 0.0, s, tx,
            0.0, 1.0, 0.0, ty,
            -s, 0.0, c, tz,
            0.0, 0.0, 0.0, 1.0,
        )
        return Mat4(m)
    }
}
