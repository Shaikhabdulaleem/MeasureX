package com.aymakan.measurex.m9capture

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.view.GestureDetector
import android.view.MotionEvent
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.ar.core.CameraConfig
import com.google.ar.core.CameraConfigFilter
import com.google.ar.core.Config
import com.google.ar.core.Frame
import com.google.ar.core.Plane
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import java.io.File
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
    private var installRequested = false

    private val jpegWriter = Executors.newSingleThreadExecutor()
    private val pendingTap = AtomicReference<FloatArray?>(null)

    // Capture state (mutated on the GL thread; UI reads via runOnUiThread).
    private enum class Phase { BEFORE_TARGET, CAPTURING, COMPLETE }
    @Volatile private var phase = Phase.BEFORE_TARGET
    private var target: DoubleArray? = null
    private var supportPlane: SupportPlane? = null
    private var controller: CaptureController? = null
    private val frames = mutableListOf<RawFrameData>()
    private var sweepIndex = 1
    private var sessionDir: File? = null
    private var cameraConfigInfo: Map<String, Any?> = emptyMap()
    private var trackingInterruptions = 0
    private var lastTracking = true

    // UI
    private lateinit var statusText: TextView
    private lateinit var instructionText: TextView
    private lateinit var setTargetButton: Button
    private lateinit var exportButton: Button
    private lateinit var newSweepButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        when (val state = ArCoreAvailabilityChecker.check(this)) {
            is ArCoreAvailabilityChecker.State.UnsupportedDevice -> {
                showBlocking()
                return
            }
            else -> if (ArCoreAvailabilityChecker.isBlocked(state)) {
                showBlocking(); return
            }
        }

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
    }

    private fun showBlocking() {
        setContentView(R.layout.activity_blocked)
    }

    override fun onResume() {
        super.onResume()
        if (!::surfaceView.isInitialized) return
        if (!hasCameraPermission()) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), 1)
            return
        }
        try {
            if (session == null) {
                when (ArCoreAvailabilityChecker.requestInstall(this, !installRequested)) {
                    com.google.ar.core.ArCoreApk.InstallStatus.INSTALL_REQUESTED -> {
                        installRequested = true; return
                    }
                    com.google.ar.core.ArCoreApk.InstallStatus.INSTALLED -> Unit
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
        session?.close()
        session = null
        jpegWriter.shutdown()
        super.onDestroy()
    }

    private fun createSession(): Session {
        val s = Session(this)
        // Prefer a stable 30 FPS config with the highest practical CPU image size.
        val filter = CameraConfigFilter(s)
            .setTargetFps(java.util.EnumSet.of(CameraConfig.TargetFps.TARGET_FPS_30))
        val configs = s.getSupportedCameraConfigs(filter)
        val chosen = configs.maxByOrNull { it.imageSize.width.toLong() * it.imageSize.height }
        if (chosen != null) {
            s.cameraConfig = chosen
            cameraConfigInfo = cameraConfigToMap(chosen)
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
        session?.setDisplayGeometry(display?.rotation ?: 0, width, height)
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
        val p = hit.hitPose
        target = doubleArrayOf(p.tx().toDouble(), p.ty().toDouble(), p.tz().toDouble())

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
        trackingInterruptions = 0
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
            val focal = intr.focalLength
            val principal = intr.principalPoint
            val dims = intr.imageDimensions
            val frameId = "%06d".format(frames.size + 1)
            val az = ctrl.accept(centre)

            val bmp = YuvToRgb.toBitmap(image)
            val out = Exporter.frameFile(sessionDir!!, frameId)
            jpegWriter.execute {
                try {
                    java.io.FileOutputStream(out).use {
                        bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 95, it)
                    }
                } finally {
                    bmp.recycle()
                }
            }

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
            exportButton.isEnabled = complete
            if (complete) phase = Phase.COMPLETE
        }
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
            guidanceTargetWorld = target?.toList(),
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
            field("candidate_count", frames.size)
            field("view_coverage_deg", ctrl.coverageDeg())
            field("total_camera_travel_mm", ctrl.totalBaselineM() * 1000.0)
            field("support_plane_available", supportPlane != null)
            field("tracking_interruptions", trackingInterruptions)
            field("sweep_index", sweepIndex)
        }
        return j.toString()
    }

    private fun startNewSweep() {
        // Fresh target + fresh tracking session so each sweep estimates world origin
        // and scale independently (poses are never averaged across sessions).
        sweepIndex++
        phase = Phase.BEFORE_TARGET
        target = null
        supportPlane = null
        controller = null
        frames.clear()
        session?.let { runCatching { it.pause() }; runCatching { it.resume() } }
        runOnUiThread { exportButton.isEnabled = false }
    }

    private fun hasCameraPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (!hasCameraPermission()) {
            Toast.makeText(this, R.string.camera_required, Toast.LENGTH_LONG).show()
            finish()
        }
    }

    private fun distance(a: DoubleArray, b: DoubleArray): Double {
        val dx = a[0] - b[0]; val dy = a[1] - b[1]; val dz = a[2] - b[2]
        return kotlin.math.sqrt(dx * dx + dy * dy + dz * dz)
    }

    companion object {
        // ARCore delivers the CPU image for the frame it came from; the delta is ~0.
        private const val TIMESTAMP_SLACK_NS = 5_000_000L
    }
}
