package com.aymakan.measurex.m9capture

/**
 * A 4x4 matrix stored **row-major** as 16 doubles (`m[row * 4 + col]`), used for
 * all M9 pose math on-device. Pure Kotlin — no Android or ARCore types — so the
 * mandatory coordinate-convention tests run on the plain JVM.
 *
 * Why a dedicated type: ARCore's [com.google.ar.core.Pose.toMatrix] writes an
 * OpenGL-style **column-major** float array; serialising that array as JSON rows
 * would transpose the matrix. [fromColumnMajor] converts the storage order
 * correctly, once, so everything downstream is ordinary row-major math.
 */
class Mat4(val m: DoubleArray) {

    init {
        require(m.size == 16) { "Mat4 needs 16 elements, got ${m.size}" }
    }

    operator fun get(row: Int, col: Int): Double = m[row * 4 + col]

    /** Matrix product `this @ other`. */
    operator fun times(other: Mat4): Mat4 {
        val r = DoubleArray(16)
        for (i in 0 until 4) {
            for (j in 0 until 4) {
                var s = 0.0
                for (k in 0 until 4) s += this[i, k] * other[k, j]
                r[i * 4 + j] = s
            }
        }
        return Mat4(r)
    }

    /** Apply to a homogeneous point/vector `(x, y, z, w)`. Returns `(x, y, z, w)`. */
    fun transform(x: Double, y: Double, z: Double, w: Double): DoubleArray {
        val out = DoubleArray(4)
        for (i in 0 until 4) {
            out[i] = this[i, 0] * x + this[i, 1] * y + this[i, 2] * z + this[i, 3] * w
        }
        return out
    }

    /** World-frame translation column `(tx, ty, tz)` — for a pose, the camera centre. */
    fun translation(): DoubleArray = doubleArrayOf(this[0, 3], this[1, 3], this[2, 3])

    /** Determinant of the top-left 3x3 rotation block (must be +1 for a proper pose). */
    fun rotationDeterminant(): Double {
        val a = this[0, 0]; val b = this[0, 1]; val c = this[0, 2]
        val d = this[1, 0]; val e = this[1, 1]; val f = this[1, 2]
        val g = this[2, 0]; val h = this[2, 1]; val i = this[2, 2]
        return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    }

    /**
     * Inverse of a rigid transform `[R|t]`, computed as `[Rᵀ | -Rᵀ t]` (exact and
     * cheap — never a general numeric inverse). For a camera pose this returns
     * `T_camera_from_world`.
     */
    fun invertRigid(): Mat4 {
        val r = DoubleArray(16)
        // Rᵀ.
        for (i in 0 until 3) for (j in 0 until 3) r[i * 4 + j] = this[j, i]
        // -Rᵀ t.
        val t = translation()
        for (i in 0 until 3) {
            r[i * 4 + 3] = -(r[i * 4 + 0] * t[0] + r[i * 4 + 1] * t[1] + r[i * 4 + 2] * t[2])
        }
        r[15] = 1.0
        return Mat4(r)
    }

    /** Nested row-major lists, ready for JSON serialisation. */
    fun toRows(): List<List<Double>> =
        (0 until 4).map { i -> (0 until 4).map { j -> this[i, j] } }

    companion object {
        fun identity(): Mat4 {
            val r = DoubleArray(16)
            for (i in 0 until 4) r[i * 4 + i] = 1.0
            return Mat4(r)
        }

        /**
         * Build a mathematical row-major [Mat4] from an **OpenGL column-major** array
         * (as written by [com.google.ar.core.Pose.toMatrix]). Column-major storage has
         * element `(row, col)` at index `col * 4 + row`, so we read it back transposed
         * into row-major order.
         */
        fun fromColumnMajor(a: FloatArray): Mat4 {
            require(a.size == 16) { "column-major array needs 16 elements, got ${a.size}" }
            val r = DoubleArray(16)
            for (col in 0 until 4) {
                for (row in 0 until 4) {
                    r[row * 4 + col] = a[col * 4 + row].toDouble()
                }
            }
            return Mat4(r)
        }

        /** Diagonal 4x4 with the given diagonal and 1 in the homogeneous slot. */
        fun diagonal(d0: Double, d1: Double, d2: Double, d3: Double = 1.0): Mat4 {
            val r = DoubleArray(16)
            r[0] = d0; r[5] = d1; r[10] = d2; r[15] = d3
            return Mat4(r)
        }
    }
}
