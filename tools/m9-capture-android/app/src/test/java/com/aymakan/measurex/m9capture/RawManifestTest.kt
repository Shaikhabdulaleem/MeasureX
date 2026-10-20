package com.aymakan.measurex.m9capture

import org.json.JSONObject
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.Test

/**
 * The raw manifest serialises to the exact `raw_capture.json` contract the offline
 * Python validator expects. Parsed back with org.json (bundled with the JVM test
 * runtime via the json dependency) to assert structure and the pose convention.
 */
class RawManifestTest {

    private fun sampleFrame(id: String, ts: Long): RawFrameData = RawFrameData(
        frameId = id,
        frameTimestampNs = ts,
        imageTimestampNs = ts,
        image = "frames/$id.jpg",
        intrinsics = RawIntrinsics(fx = 1000.0, fy = 1000.5, cx = 320.0, cy = 240.0, width = 640, height = 480),
        tWorldFromCamera = PoseConvention.arcoreToM9Pose(Mat4.identity()),
        trackingState = "TRACKING",
        guidanceAngleDeg = 12.5,
        cameraDistanceToTargetM = 1.5,
    )

    private fun sampleManifest(): RawManifest = RawManifest(
        gravityWorld = listOf(0.0, -1.0, 0.0),
        device = DeviceInfo(
            manufacturer = "samsung", model = "SM-A165F",
            androidVersion = "14", arcoreVersion = "1.48.0",
            cameraConfig = mapOf("fps" to 30, "cpu_image_width" to 640, "cpu_image_height" to 480),
        ),
        guidanceTargetWorld = listOf(0.0, 0.12, 0.0),
        supportPlane = SupportPlane(normal = listOf(0.0, 1.0, 0.0), offset = 0.0),
        frames = listOf(sampleFrame("000001", 1_000_000_000L), sampleFrame("000002", 1_033_000_000L)),
    )

    @Test
    fun serialisesRequiredContractFields() {
        val o = JSONObject(sampleManifest().toJson())
        assertEquals(1, o.getInt("schema_version"))
        assertEquals("m9_real_raw", o.getString("capture_type"))
        assertEquals("arcore", o.getString("pose_source"))
        assertEquals("T_world_from_camera", o.getString("pose_convention"))
        assertEquals("opencv_x_right_y_down_z_forward", o.getString("camera_convention"))
        assertEquals("meters", o.getString("units"))
        assertEquals(-1.0, o.getJSONArray("gravity_world").getDouble(1), 1e-9)
    }

    @Test
    fun serialisesPoseAsRowMajor4x4() {
        val o = JSONObject(sampleManifest().toJson())
        val f0 = o.getJSONArray("frames").getJSONObject(0)
        val mat = f0.getJSONArray("T_world_from_camera")
        assertEquals(4, mat.length())
        assertEquals(4, mat.getJSONArray(0).length())
        // M9 pose of an identity ARCore pose is diag(1,-1,-1,1).
        assertEquals(1.0, mat.getJSONArray(0).getDouble(0), 1e-9)
        assertEquals(-1.0, mat.getJSONArray(1).getDouble(1), 1e-9)
        assertEquals(-1.0, mat.getJSONArray(2).getDouble(2), 1e-9)
    }

    @Test
    fun serialisesIntrinsicsAndTimestamps() {
        val o = JSONObject(sampleManifest().toJson())
        val f0 = o.getJSONArray("frames").getJSONObject(0)
        val k = f0.getJSONObject("intrinsics")
        assertEquals(640, k.getInt("width"))
        assertEquals(480, k.getInt("height"))
        assertEquals(0L, f0.getLong("timestamp_delta_ns"))
        assertEquals("TRACKING", f0.getString("tracking_state"))
    }

    @Test
    fun supportPlaneNullableSerialisesExplicitly() {
        val noPlane = sampleManifest().copy(supportPlane = null, guidanceTargetWorld = null)
        val o = JSONObject(noPlane.toJson())
        assertTrue(o.isNull("support_plane"))
        assertTrue(o.isNull("guidance_target_world"))
    }
}
