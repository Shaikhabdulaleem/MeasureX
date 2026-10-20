package com.aymakan.measurex.m9capture

import android.Manifest
import android.content.pm.PackageManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.GestureDetector
import android.view.MotionEvent
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.ar.core.Anchor
import com.google.ar.core.ArCoreApk
import com.google.ar.core.CameraConfig
import com.google.ar.core.CameraConfigFilter
import com.google.ar.core.Config
import com.google.ar.core.Frame
import com.google.ar.core.Plane
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/**
 * The M9 data-capture instrument. It records real RGB frames, metric ARCore camera
 * poses (converted to the M9 convention), per-frame intrinsics, gravity and an
 * optional support plane. It computes **no** dimensions, runs no segmentation and
 * talks to no backend. If ARCore is unavailable it blocks with a clear message and
 * never falls back to monocular depth.
 */
class CaptureActivity : AppCompatActivity(), GLSurfaceView.Renderer {

    private lateinit var surfaceView: GLSurfaceView
    private val background = BackgroundRenderer()
    private var session: Session? = null
    private var sessionId: String = ""
    private var installRequested = false

    private val jpegWriter = Executors.newSingleThreadExecutor()
    private val pendingTap = AtomicReference<FloatArray?>(null)
    private val mainHandler = Handler(Looper.getMainLooper())
    private var availabilityChecks = 0

    // Capture state (mutated on the GL thread; UI reads via runOnUiThread).
    private enum class Phase { BEFORE_TARGET, CAPTURING, COMPLETE }
    @Volatile private var phase = Phase.BEFORE_TARGET
    private var target: DoubleArray? = null
    private var targetAnchor: Anchor? = null
    @Volatile private var guidanceTargetWorld: DoubleArray? = null
    private var supportPlane: SupportPlane? = null
    private var controller: CaptureController? = null
    private val frames = mutableListOf<RawFrameData>()
    private val frameIds = FrameIds()
    private val writes = JpegWrites()
    private var sweepIndex = 1
    private var sessionDir: File? = null
    private var cameraConfigInfo: Map<String, Any?> = emptyMap()
    private var cameraId: String? = null
    private var sensorOrientation: Int? = null
    private var trackingInterruptions = 0
    private var lastTracking = true

    // Orientation / image diagnostics (last observed accepted/attempted frame).
    private var displayRotation = 0
    private var viewportWidth = 0
    private var viewportHeight = 0
    private var cpuImageWidth = 0
    private var cpuImageHeight = 0
    private var intrinsicsWidth = 0
    private var intrinsicsHeight = 0
    private var rejectedDimMismatch = 0

    // UI
    private lateinit var statusText: TextView
    private lateinit var instructionText: TextView
    private lateinit var setTargetButton: Button
    private lateinit var exportButton: Button
    private lateinit var newSweepButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        resolveAvailabilityAndStart()
    }

    /**
     * Branch on ARCore availability. UNKNOWN_CHECKING is still being resolved
     * asynchronously, so show a message and recheck on the main looper (bounded, not a
     * busy loop) instead of requesting install as if support were known; a hard
     * error/timeout or unsupported device blocks cleanly.
     */
    private fun resolveAvailabilityAndStart() {
        when (ArCoreAvailabilityChecker.startupAction(ArCoreAvailabilityChecker.check(this))) {
            ArCoreAvailabilityChecker.StartupAction.BLOCK -> showBlocking(getString(R.string.blocked_message))
            ArCoreAvailabilityChecker.StartupAction.RECHECK -> {
                showBlocking(getString(R.string.checking_support))
                if (availabilityChecks++ < MAX_AVAILABILITY_CHECKS) {
                    mainHandler.postDelayed({ resolveAvailabilityAndStart() }, AVAILABILITY_RECHECK_MS)
                } else {
                    showBlocking(getString(R.string.blocked_message))  // timed out determining support
                }
            }
            ArCoreAvailabilityChecker.StartupAction.PROCEED -> startCapture()
        }
    }

    private fun startCapture() {
        if (::surfaceView.isInitialized) return  // already started (recheck fired twice)
        setContentView(R.layout.activity_capture)
        surfaceView = findViewById(R.id.surface)
        statusText = findViewById(R.id.status)
        instructionText = findViewById(R.id.instruction)
        setTargetButton = findViewById(R.id.set_target)
        exportButton = findViewById(R.id.export)
        newSweepButton = findViewById(R.id.new_sweep)

        surfaceView.preserveEGLContextOnPause = true
        surfaceView.setEGLContextClientVersion(2)
        surfaceView.setEGLConfigChooser(8, 8, 8, 8, 16, 0)
        surfaceView.setRenderer(this)
        surfaceView.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY

        val gesture = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onSingleTapUp(e: MotionEvent): Boolean {
                pendingTap.set(floatArrayOf(e.x, e.y)); return true
            }
            override fun onDown(e: MotionEvent) = true
        })
        surfaceView.setOnTouchListener { _, e -> gesture.onTouchEvent(e) }

        setTargetButton.setOnClickListener {
            Toast.makeText(this, R.string.aim_then_tap, Toast.LENGTH_SHORT).show()
        }
        exportButton.setOnClickListener { exportCurrentSweep() }
        newSweepButton.setOnClickListener { startNewSweep() }
        exportButton.isEnabled = false

        ensureSessionStarted()  // onResume has already run if we got here via a recheck.
    }

    private fun showBlocking(message: String) {
        setContentView(R.layout.activity_blocked)
        findViewById<TextView>(R.id.blocked_text)?.text = message
    }

    override fun onResume() {
        super.onResume()
        ensureSessionStarted()
    }

    /**
     * Create (once) and resume the ARCore session. Reusable so it runs from both
     * [onResume] and [onRequestPermissionsResult]: if permission is granted while the
     * activity is already resumed, the session is started immediately rather than only
     * on a later resume. Guards against duplicate session creation.
     */
    private fun ensureSessionStarted() {
        if (!::surfaceView.isInitialized) return
        if (!hasCameraPermission()) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), CAMERA_REQUEST)
            return
        }
        try {
            if (session == null) {
                when (ArCoreAvailabilityChecker.requestInstall(this, !installRequested)) {
                    ArCoreApk.InstallStatus.INSTALL_REQUESTED -> { installRequested = true; return }
                    ArCoreApk.InstallStatus.INSTALLED -> Unit
                }
                session = createSession()
            }
            session?.resume()
            surfaceView.onResume()
        } catch (e: Exception) {
            Toast.makeText(this, getString(R.string.arcore_error, e.message), Toast.LENGTH_LONG).show()
            finish()
        }
    }

    override fun onPause() {
        super.onPause()
        if (::surfaceView.isInitialized) {
            surfaceView.onPause()
            session?.pause()
        }
    }

    override fun onDestroy() {
        targetAnchor?.detach()
        targetAnchor = null
        session?.close()
        session = null
        jpegWriter.shutdown()
        mainHandler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun createSession(): Session {
        val s = Session(this)
        sessionId = UUID.randomUUID().toString()  // a distinct id for every ARCore session
        // Prefer a stable 30 FPS config with the highest practical CPU image size.
        val filter = CameraConfigFilter(s)
            .setTargetFps(java.util.EnumSet.of(CameraConfig.TargetFps.TARGET_FPS_30))
        val configs = s.getSupportedCameraConfigs(filter)
        val chosen = configs.maxByOrNull { it.imageSize.width.toLong() * it.imageSize.height }
        if (chosen != null) {
            s.cameraConfig = chosen
            cameraConfigInfo = cameraConfigToMap(chosen)
            cameraId = chosen.cameraId
            sensorOrientation = sensorOrientationOf(chosen.cameraId)
        }
        val config = Config(s).apply {
            focusMode = Config.FocusMode.AUTO
            planeFindingMode = Config.PlaneFindingMode.HORIZONTAL
            // Metric scale comes from VIO pose translations only — depth is never used.
            depthMode = Config.DepthMode.DISABLED
            updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
        }
        s.configure(config)
        return s
    }

    /** Sensor mounting rotation (deg) of the chosen physical camera, or null if the
     *  platform does not expose it cleanly. Never fabricated. */
    private fun sensorOrientationOf(arcoreCameraId: String?): Int? = runCatching {
        val cm = getSystemService(CameraManager::class.java) ?: return null
        val id = arcoreCameraId?.takeIf { it in cm.cameraIdList } ?: return null
        cm.getCameraCharacteristics(id).get(CameraCharacteristics.SENSOR_ORIENTATION)
    }.getOrNull()

    private fun cameraConfigToMap(c: CameraConfig): Map<String, Any?> = mapOf(
        "cpu_image_width" to c.imageSize.width,
        "cpu_image_height" to c.imageSize.height,
        "gpu_texture_width" to c.textureSize.width,
        "gpu_texture_height" to c.textureSize.height,
        "fps_range" to "30",
        "camera_id" to c.cameraId,
    )

    // ------------------------------------------------------------------ GL --- //

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        background.createOnGlThread()
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
        displayRotation = display?.rotation ?: 0
        viewportWidth = width
        viewportHeight = height
        session?.setDisplayGeometry(displayRotation, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT or GLES20.GL_DEPTH_BUFFER_BIT)
        val s = session ?: return
        s.setCameraTextureName(background.textureId)
        val frame: Frame = try {
            s.update()
        } catch (_: Exception) {
            return
        }
        background.draw(frame)

        val camera = frame.camera
        val tracking = camera.trackingState == TrackingState.TRACKING
        if (!tracking && lastTracking) trackingInterruptions++
        lastTracking = tracking
        if (!tracking) {
            setStatus(getString(R.string.tracking_lost), "")
            return
        }

        // Sample the tracked anchor's pose each frame on the GL thread; export reads
        // this latest value (see guidance_target_world documentation).
        targetAnchor?.takeIf { it.trackingState == TrackingState.TRACKING }?.let { a ->
            val p = a.pose
            guidanceTargetWorld = doubleArrayOf(p.tx().toDouble(), p.ty().toDouble(), p.tz().toDouble())
        }

        pendingTap.getAndSet(null)?.let { tap -> handleTap(frame, tap) }

        when (phase) {
            Phase.BEFORE_TARGET ->
                setStatus(getString(R.string.aim_then_tap), getString(R.string.instr_set_target))
            Phase.CAPTURING -> maybeCaptureCandidate(frame)
            Phase.COMPLETE -> Unit
        }
    }

    private fun handleTap(frame: Frame, tap: FloatArray) {
        if (phase != Phase.BEFORE_TARGET) return
        val hits = frame.hitTest(tap[0], tap[1])
        // Prefer an upward-facing horizontal plane (the table/conveyor under the box).
        val planeHit = hits.firstOrNull {
            val t = it.trackable
            t is Plane && t.type == Plane.Type.HORIZONTAL_UPWARD_FACING && t.isPoseInPolygon(it.hitPose)
        }
        val hit = planeHit ?: hits.firstOrNull() ?: return

        // A real ARCore anchor stabilises the target across the sweep. It is a guidance
        // pivot only — it imposes no dimensions.
        targetAnchor?.detach()
        targetAnchor = hit.createAnchor()
        val p = targetAnchor!!.pose
        target = doubleArrayOf(p.tx().toDouble(), p.ty().toDouble(), p.tz().toDouble())
        guidanceTargetWorld = target!!.copyOf()

        val trackable = hit.trackable
        if (planeHit != null && trackable is Plane) {
            val centre = trackable.centerPose
            val normalUp = doubleArrayOf(
                centre.yAxis[0].toDouble(), centre.yAxis[1].toDouble(), centre.yAxis[2].toDouble()
            )
            val pointOnPlane = doubleArrayOf(
                centre.tx().toDouble(), centre.ty().toDouble(), centre.tz().toDouble()
            )
            supportPlane = PoseConvention.supportPlane(pointOnPlane, normalUp)
        } else {
            // Only a feature point — usable as a guidance target, NOT a support plane.
            supportPlane = null
        }

        controller = CaptureController(target!!)
        sessionDir = Exporter.newSessionDir(this, sweepIndex)
        frames.clear()
        frameIds.reset()
        writes.clear()
        trackingInterruptions = 0
        rejectedDimMismatch = 0
        phase = Phase.CAPTURING
    }

    private fun maybeCaptureCandidate(frame: Frame) {
        val ctrl = controller ?: return
        val camera = frame.camera
        val centreArr = FloatArray(16)
        camera.pose.toMatrix(centreArr, 0)
        val m9Pose = PoseConvention.m9PoseFromArcoreColumnMajor(centreArr)
        val centre = m9Pose.translation()
        if (!ctrl.shouldAccept(centre)) {
            updateProgress(ctrl); return
        }

        val image = try {
            frame.acquireCameraImage()
        } catch (_: Exception) {
            return  // image not ready this frame — try next
        }
        try {
            val delta = frame.timestamp - image.timestamp
            if (kotlin.math.abs(delta) > TIMESTAMP_SLACK_NS) return  // reject unsynced pair

            val intr = camera.imageIntrinsics
            val dims = intr.imageDimensions
            cpuImageWidth = image.width; cpuImageHeight = image.height
            intrinsicsWidth = dims[0]; intrinsicsHeight = dims[1]
            // The saved image is never rotated/mirrored/cropped/resized, so its pixel
            // grid must equal the declared intrinsics grid. A mismatch means a native
            // orientation bug — reject the candidate and record it.
            if (!imageMatchesIntrinsics(image.width, image.height, dims[0], dims[1])) {
                rejectedDimMismatch++
                updateProgress(ctrl)
                return
            }

            val focal = intr.focalLength
            val principal = intr.principalPoint
            val frameId = frameIds.next()
            val az = ctrl.accept(centre, frameId)

            val bmp = YuvToRgb.toBitmap(image)
            val out = Exporter.frameFile(sessionDir!!, frameId)
            writes.begin(frameId)
            jpegWriter.execute { writeJpeg(frameId, bmp, out) }

            frames.add(
                RawFrameData(
                    frameId = frameId,
                    frameTimestampNs = frame.timestamp,
                    imageTimestampNs = image.timestamp,
                    image = "frames/$frameId.jpg",
                    intrinsics = RawIntrinsics(
                        fx = focal[0].toDouble(), fy = focal[1].toDouble(),
                        cx = principal[0].toDouble(), cy = principal[1].toDouble(),
                        width = dims[0], height = dims[1],
                    ),
                    tWorldFromCamera = m9Pose,
                    trackingState = "TRACKING",
                    guidanceAngleDeg = az,
                    cameraDistanceToTargetM = distance(centre, target!!),
                )
            )
            updateProgress(ctrl)
        } finally {
            image.close()  // ARCore limits simultaneously-acquired images — always close.
        }
    }

    /** Compress one candidate's bitmap; resolve its write state (OK or FAILED). On
     *  failure the frame is dropped from the manifest + controller on the GL thread so
     *  it is never a valid manifest frame and can be replaced by a later viewpoint. */
    private fun writeJpeg(frameId: String, bmp: android.graphics.Bitmap, out: File) {
        val ok = try {
            java.io.FileOutputStream(out).use { bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 95, it) }
            out.isFile && out.length() > 0L
        } catch (_: Exception) {
            false
        } finally {
            bmp.recycle()
        }
        if (ok) {
            writes.succeed(frameId)
        } else {
            writes.fail(frameId)
            surfaceView.queueEvent {
                controller?.remove(frameId)
                frames.removeAll { it.frameId == frameId }
                writes.forget(frameId)              // no longer referenced → stops blocking export
                runCatching { out.delete() }
                if (controller?.isComplete() != true) phase = Phase.CAPTURING  // re-open a lost sweep
            }
            runOnUiThread { Toast.makeText(this, R.string.frame_write_failed, Toast.LENGTH_SHORT).show() }
        }
        runOnUiThread { refreshExportEnabled() }
    }

    private fun updateProgress(ctrl: CaptureController) {
        val cov = ctrl.coverageDeg()
        val complete = ctrl.isComplete()
        val instr = when {
            complete -> getString(R.string.coverage_reached)
            cov < ctrl.minCoverageDeg / 2 -> getString(R.string.move_around)
            else -> getString(R.string.continue_around)
        }
        runOnUiThread {
            statusText.text = getString(R.string.capture_status, frames.size, cov.toInt(), trackingInterruptions)
            instructionText.text = instr
            if (complete) phase = Phase.COMPLETE
            refreshExportEnabled()
        }
    }

    /** Export is enabled only once coverage is complete AND every candidate image has
     *  finished writing with no failure pending — never while a JPEG write is in
     *  flight. Re-evaluated on each progress tick and on each write completion. */
    private fun refreshExportEnabled() {
        exportButton.isEnabled = phase == Phase.COMPLETE && writes.exportReady()
    }

    private fun setStatus(status: String, instruction: String) {
        runOnUiThread {
            statusText.text = status
            instructionText.text = instruction
        }
    }

    private fun exportCurrentSweep() {
        val dir = sessionDir ?: return
        val ctrl = controller ?: return
        if (phase != Phase.COMPLETE || !writes.exportReady()) {
            Toast.makeText(this, R.string.export_wait_writes, Toast.LENGTH_SHORT).show()
            return
        }
        val referenced = frames.map { it.frameId }
        // Defensive: a duplicate frame id means an allocation bug; refuse rather than
        // export a manifest whose images collide on disk.
        if (referenced.size != referenced.toSet().size) {
            Toast.makeText(this, R.string.export_incomplete, Toast.LENGTH_SHORT).show()
            return
        }
        // Final guard: never ZIP until every referenced image is present and non-empty.
        if (!Exporter.allFramesPresent(dir, referenced)) {
            Toast.makeText(this, R.string.export_wait_writes, Toast.LENGTH_SHORT).show()
            return
        }

        val manifest = RawManifest(
            gravityWorld = PoseConvention.GRAVITY_WORLD.toList(),
            device = DeviceInfo(
                manufacturer = android.os.Build.MANUFACTURER,
                model = android.os.Build.MODEL,
                androidVersion = android.os.Build.VERSION.RELEASE,
                arcoreVersion = runCatching {
                    packageManager.getPackageInfo("com.google.ar.core", 0).versionName ?: "unknown"
                }.getOrDefault("unknown"),
                cameraConfig = cameraConfigInfo,
            ),
            // The target anchor's pose, sampled on the render thread at the latest
            // tracked frame before this export (see guidanceTargetWorld), in the same
            // world frame as the exported camera poses.
            guidanceTargetWorld = (guidanceTargetWorld ?: target)?.toList(),
            supportPlane = supportPlane,
            frames = frames.toList(),
        )
        Exporter.writeText(File(dir, "raw_capture.json"), manifest.toJson())
        Exporter.writeText(File(dir, "diagnostics.json"), diagnosticsJson(ctrl))
        val zip = Exporter.zip(dir)
        startActivity(android.content.Intent.createChooser(Exporter.shareIntent(this, zip), "Share M9 capture"))
        Toast.makeText(this, getString(R.string.exported_to, dir.absolutePath), Toast.LENGTH_LONG).show()
    }

    private fun diagnosticsJson(ctrl: CaptureController): String {
        val j = JsonWriter()
        j.obj {
            field("session_id", sessionId)
            field("sweep_index", sweepIndex)
            field("candidate_count", frames.size)
            field("view_coverage_deg", ctrl.coverageDeg())
            field("total_camera_travel_mm", ctrl.totalBaselineM() * 1000.0)
            field("support_plane_available", supportPlane != null)
            field("tracking_interruptions", trackingInterruptions)
            field("rejected_dim_mismatch", rejectedDimMismatch)
            // Native image-orientation diagnostics. The saved image stays unrotated.
            field("display_rotation", displayRotation)
            field("cpu_image_width", cpuImageWidth)
            field("cpu_image_height", cpuImageHeight)
            field("intrinsics_width", intrinsicsWidth)
            field("intrinsics_height", intrinsicsHeight)
            field("camera_id", cameraId ?: "unknown")
            if (sensorOrientation != null) field("sensor_orientation_deg", sensorOrientation!!)
            else nullField("sensor_orientation_deg")
            rawField("camera_config", JsonWriter.anyMap(cameraConfigInfo))
        }
        return j.toString()
    }

    private fun startNewSweep() {
        // Refuse while JPEG writes from the current sweep are still in flight: clearing
        // the write tracker now would let a stale writer callback mutate the new sweep's
        // state. The user retries once writes finish.
        if (writes.pending() > 0) {
            Toast.makeText(this, R.string.new_sweep_wait_writes, Toast.LENGTH_SHORT).show()
            return
        }
        runOnUiThread { exportButton.isEnabled = false }
        // Clear state and recreate the ARCore session on the GL thread so each sweep
        // initialises VIO (world origin + metric scale) independently; poses are never
        // averaged across sessions.
        surfaceView.queueEvent {
            sweepIndex++
            phase = Phase.BEFORE_TARGET
            target = null
            guidanceTargetWorld = null
            supportPlane = null
            controller = null
            frames.clear()
            frameIds.reset()
            writes.clear()
            trackingInterruptions = 0
            rejectedDimMismatch = 0
            recreateSession()
        }
    }

    /** Tear down the current ARCore session and stand up a brand-new one (new
     *  session_id, fresh VIO). Runs on the GL thread. */
    private fun recreateSession() {
        val old = session
        session = null
        targetAnchor?.detach()
        targetAnchor = null
        runCatching { old?.pause() }
        runCatching { old?.close() }
        try {
            val s = createSession()
            if (viewportWidth > 0) s.setDisplayGeometry(displayRotation, viewportWidth, viewportHeight)
            s.setCameraTextureName(background.textureId)
            s.resume()
            session = s
        } catch (e: Exception) {
            runOnUiThread {
                Toast.makeText(this, getString(R.string.arcore_error, e.message), Toast.LENGTH_LONG).show()
                finish()
            }
        }
    }

    private fun hasCameraPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (hasCameraPermission()) {
            // Granted while already resumed — start the session now, not on a later resume.
            ensureSessionStarted()
        } else {
            Toast.makeText(this, R.string.camera_required, Toast.LENGTH_LONG).show()
            finish()
        }
    }

    private fun distance(a: DoubleArray, b: DoubleArray): Double {
        val dx = a[0] - b[0]; val dy = a[1] - b[1]; val dz = a[2] - b[2]
        return kotlin.math.sqrt(dx * dx + dy * dy + dz * dz)
    }

    companion object {
        private const val CAMERA_REQUEST = 1
        // ARCore delivers the CPU image for the frame it came from; the delta is ~0.
        private const val TIMESTAMP_SLACK_NS = 5_000_000L
        private const val AVAILABILITY_RECHECK_MS = 200L
        private const val MAX_AVAILABILITY_CHECKS = 25  // ~5 s of "checking" before blocking
    }
}
