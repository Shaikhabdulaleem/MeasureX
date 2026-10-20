package com.aymakan.measurex.m9capture

/**
 * The `raw_capture.json` data model and its serialisation. Pure Kotlin with a tiny
 * hand-rolled JSON writer (no Android/org.json dependency) so it is unit-tested on
 * the plain JVM.
 *
 * This is the **raw** bundle (`capture_type == "m9_real_raw"`): real RGB frames,
 * metric ARCore poses already converted to the M9 convention, per-frame intrinsics,
 * gravity and an optional support plane — but **no masks and no dimensions**. The
 * offline pipeline segments it into the strict `capture.json` the fitter consumes.
 */
data class RawIntrinsics(
    val fx: Double, val fy: Double, val cx: Double, val cy: Double,
    val width: Int, val height: Int,
)

data class SupportPlane(val normal: List<Double>, val offset: Double)

data class RawFrameData(
    val frameId: String,
    val frameTimestampNs: Long,
    val imageTimestampNs: Long,
    val image: String,
    val intrinsics: RawIntrinsics,
    /** `T_world_from_camera` in the M9 convention — already converted from ARCore. */
    val tWorldFromCamera: Mat4,
    val trackingState: String,
    val guidanceAngleDeg: Double?,
    val cameraDistanceToTargetM: Double?,
) {
    val timestampDeltaNs: Long get() = frameTimestampNs - imageTimestampNs
}

data class DeviceInfo(
    val manufacturer: String,
    val model: String,
    val androidVersion: String,
    val arcoreVersion: String,
    val cameraConfig: Map<String, Any?> = emptyMap(),
)

data class RawManifest(
    val gravityWorld: List<Double>,
    val device: DeviceInfo,
    val guidanceTargetWorld: List<Double>?,
    val supportPlane: SupportPlane?,
    val frames: List<RawFrameData>,
    val poseSource: String = "arcore",
) {
    fun toJson(): String {
        val j = JsonWriter()
        j.obj {
            field("schema_version", 1)
            field("capture_type", "m9_real_raw")
            field("pose_source", poseSource)
            field("pose_convention", "T_world_from_camera")
            field("camera_convention", "opencv_x_right_y_down_z_forward")
            field("units", "meters")
            arrayField("gravity_world", gravityWorld)
            rawField("device", deviceJson(device))
            if (guidanceTargetWorld != null) arrayField("guidance_target_world", guidanceTargetWorld)
            else nullField("guidance_target_world")
            if (supportPlane != null) rawField("support_plane", supportPlaneJson(supportPlane))
            else nullField("support_plane")
            rawField("frames", framesJson(frames))
        }
        return j.toString()
    }

    private fun deviceJson(d: DeviceInfo): String {
        val j = JsonWriter()
        j.obj {
            field("manufacturer", d.manufacturer)
            field("model", d.model)
            field("android_version", d.androidVersion)
            field("arcore_version", d.arcoreVersion)
            rawField("camera_config", JsonWriter.anyMap(d.cameraConfig))
        }
        return j.toString()
    }

    private fun supportPlaneJson(p: SupportPlane): String {
        val j = JsonWriter()
        j.obj {
            arrayField("normal", p.normal)
            field("offset", p.offset)
        }
        return j.toString()
    }

    private fun framesJson(frames: List<RawFrameData>): String {
        val sb = StringBuilder("[")
        frames.forEachIndexed { i, f ->
            if (i > 0) sb.append(",")
            sb.append(frameJson(f))
        }
        return sb.append("]").toString()
    }

    private fun frameJson(f: RawFrameData): String {
        val j = JsonWriter()
        j.obj {
            field("frame_id", f.frameId)
            field("frame_timestamp_ns", f.frameTimestampNs)
            field("image_timestamp_ns", f.imageTimestampNs)
            field("timestamp_delta_ns", f.timestampDeltaNs)
            field("image", f.image)
            rawField("intrinsics", intrinsicsJson(f.intrinsics))
            rawField("T_world_from_camera", matrixJson(f.tWorldFromCamera))
            field("tracking_state", f.trackingState)
            if (f.guidanceAngleDeg != null) field("guidance_angle_deg", f.guidanceAngleDeg)
            if (f.cameraDistanceToTargetM != null) field("camera_distance_to_target_m", f.cameraDistanceToTargetM)
        }
        return j.toString()
    }

    private fun intrinsicsJson(k: RawIntrinsics): String {
        val j = JsonWriter()
        j.obj {
            field("fx", k.fx); field("fy", k.fy); field("cx", k.cx); field("cy", k.cy)
            field("width", k.width); field("height", k.height)
        }
        return j.toString()
    }

    private fun matrixJson(mat: Mat4): String {
        val sb = StringBuilder("[")
        mat.toRows().forEachIndexed { i, row ->
            if (i > 0) sb.append(",")
            sb.append("[").append(row.joinToString(",") { JsonWriter.num(it) }).append("]")
        }
        return sb.append("]").toString()
    }
}

/** Minimal JSON object writer — enough for the fixed raw manifest schema. */
class JsonWriter {
    private val sb = StringBuilder()
    private var count = 0

    fun obj(body: JsonWriter.() -> Unit): JsonWriter {
        sb.append("{"); this.body(); sb.append("}"); return this
    }

    fun field(name: String, value: String) = kv(name) { sb.append(str(value)) }
    fun field(name: String, value: Int) = kv(name) { sb.append(value.toString()) }
    fun field(name: String, value: Long) = kv(name) { sb.append(value.toString()) }
    fun field(name: String, value: Double) = kv(name) { sb.append(num(value)) }
    fun field(name: String, value: Boolean) = kv(name) { sb.append(value.toString()) }
    fun nullField(name: String) = kv(name) { sb.append("null") }
    fun rawField(name: String, rawJson: String) = kv(name) { sb.append(rawJson) }
    fun arrayField(name: String, values: List<Double>) =
        kv(name) { sb.append("[").append(values.joinToString(",") { num(it) }).append("]") }

    private fun kv(name: String, writeValue: () -> Unit) {
        if (count++ > 0) sb.append(",")
        sb.append(str(name)).append(":"); writeValue()
    }

    override fun toString(): String = sb.toString()

    companion object {
        fun num(d: Double): String =
            if (d.isFinite()) d.toString() else "null"  // JSON has no NaN/Infinity

        fun str(s: String): String {
            val b = StringBuilder("\"")
            for (c in s) when (c) {
                '\\' -> b.append("\\\\")
                '"' -> b.append("\\\"")
                '\n' -> b.append("\\n")
                '\r' -> b.append("\\r")
                '\t' -> b.append("\\t")
                else -> if (c < ' ') b.append("\\u%04x".format(c.code)) else b.append(c)
            }
            return b.append("\"").toString()
        }

        fun anyMap(map: Map<String, Any?>): String {
            val sb = StringBuilder("{")
            var i = 0
            for ((k, v) in map) {
                if (i++ > 0) sb.append(",")
                sb.append(str(k)).append(":").append(anyValue(v))
            }
            return sb.append("}").toString()
        }

        private fun anyValue(v: Any?): String = when (v) {
            null -> "null"
            is String -> str(v)
            is Int, is Long -> v.toString()
            is Double -> num(v)
            is Float -> num(v.toDouble())
            is Boolean -> v.toString()
            else -> str(v.toString())
        }
    }
}
