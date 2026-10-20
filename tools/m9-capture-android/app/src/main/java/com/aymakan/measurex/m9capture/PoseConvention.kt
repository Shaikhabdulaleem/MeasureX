package com.aymakan.measurex.m9capture

import kotlin.math.atan2
import kotlin.math.sqrt

/**
 * The single source of truth for the ARCore → MeasureX-M9 coordinate convention.
 * A bug here would invalidate every real measurement, so this is pure Kotlin and
 * covered by the mandatory [PoseConventionTest].
 *
 * **Pose.** M9 uses `X_world = T_world_from_camera @ X_camera` with the OpenCV /
 * pinhole camera frame (`+X` right, `+Y` down, `+Z` forward). ARCore's camera
 * frame is OpenGL-style (`+X` right, `+Y` up, `-Z` forward). The two differ by a
 * 180° rotation about the camera X axis:
 *
 * ```
 * C_arcore_from_m9_camera = diag(1, -1, -1, 1)
 * T_world_from_camera_M9  = T_world_from_camera_ARCore @ C_arcore_from_m9_camera
 * ```
 *
 * **Gravity.** M9's `gravity_world` is the direction gravity *points*. ARCore world
 * is gravity-aligned with `+Y` up, so `gravity_world = [0, -1, 0]` and M9's up is
 * `-gravity_world = +Y`.
 */
object PoseConvention {

    /** `diag(1, -1, -1, 1)` — a 180° rotation about the camera X axis (det = +1). */
    val C_ARCORE_FROM_M9: Mat4 = Mat4.diagonal(1.0, -1.0, -1.0, 1.0)

    /** The direction gravity points in the normal ARCore world (`+Y` up). */
    val GRAVITY_WORLD: DoubleArray = doubleArrayOf(0.0, -1.0, 0.0)

    /** Convert an ARCore `T_world_from_camera` pose into the M9 convention. */
    fun arcoreToM9Pose(tWorldFromCameraArcore: Mat4): Mat4 =
        tWorldFromCameraArcore * C_ARCORE_FROM_M9

    /**
     * Convert ARCore's **column-major** pose array (from `Pose.toMatrix`) directly
     * into an M9 `T_world_from_camera`: de-column-major first, then apply the frame
     * conversion. Never serialise the raw array as JSON rows.
     */
    fun m9PoseFromArcoreColumnMajor(columnMajor: FloatArray): Mat4 =
        arcoreToM9Pose(Mat4.fromColumnMajor(columnMajor))

    /** Gravity-up unit vector: `-gravity_world`, normalised. */
    fun upFromGravity(gravityWorld: DoubleArray = GRAVITY_WORLD): DoubleArray {
        val n = norm(gravityWorld)
        return doubleArrayOf(-gravityWorld[0] / n, -gravityWorld[1] / n, -gravityWorld[2] / n)
    }

    /**
     * Canonical metric support plane `{normal, offset}` for the equation
     * `normal · X + offset = 0`, given a world point on the plane and the plane's
     * world normal (e.g. an ARCore horizontal plane's local `+Y`). The normal is
     * unit-length and oriented gravity-up; `offset = -normal · P`. This never
     * supplies metric scale — that comes only from the camera-pose translations.
     */
    fun supportPlane(pointOnPlane: DoubleArray, planeNormalWorld: DoubleArray,
                     gravityWorld: DoubleArray = GRAVITY_WORLD): SupportPlane {
        val up = upFromGravity(gravityWorld)
        var n = unit(planeNormalWorld)
        if (dot(n, up) < 0.0) n = doubleArrayOf(-n[0], -n[1], -n[2])  // orient gravity-up
        val offset = -dot(n, pointOnPlane)
        return SupportPlane(normal = listOf(n[0], n[1], n[2]), offset = offset)
    }

    /**
     * Azimuth (degrees, (-180, 180]) of a camera centre around the target in the
     * horizontal plane defined by gravity-up — the viewpoint position on the sweep.
     * Matches the offline selector so on-device coverage and offline selection agree.
     */
    fun azimuthDeg(cameraCenter: DoubleArray, target: DoubleArray,
                   gravityWorld: DoubleArray = GRAVITY_WORLD): Double {
        val up = upFromGravity(gravityWorld)
        val (a, b) = horizontalBasis(up)
        var d = doubleArrayOf(
            cameraCenter[0] - target[0], cameraCenter[1] - target[1], cameraCenter[2] - target[2]
        )
        val h = dot(d, up)
        d = doubleArrayOf(d[0] - h * up[0], d[1] - h * up[1], d[2] - h * up[2])
        return Math.toDegrees(atan2(dot(d, b), dot(d, a)))
    }

    /** Two orthonormal axes spanning the plane perpendicular to [up]. */
    fun horizontalBasis(up: DoubleArray): Pair<DoubleArray, DoubleArray> {
        val u = unit(up)
        val seed = if (kotlin.math.abs(u[0]) < 0.9) doubleArrayOf(1.0, 0.0, 0.0)
        else doubleArrayOf(0.0, 1.0, 0.0)
        val p = dot(seed, u)
        var e1 = doubleArrayOf(seed[0] - p * u[0], seed[1] - p * u[1], seed[2] - p * u[2])
        e1 = unit(e1)
        val e2 = cross(u, e1)
        return Pair(e1, e2)
    }

    private fun dot(a: DoubleArray, b: DoubleArray) = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    private fun norm(a: DoubleArray) = sqrt(dot(a, a))
    private fun unit(a: DoubleArray): DoubleArray {
        val n = norm(a); return doubleArrayOf(a[0] / n, a[1] / n, a[2] / n)
    }
    private fun cross(a: DoubleArray, b: DoubleArray) = doubleArrayOf(
        a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]
    )
}
