package com.aymakan.measurex.m9capture

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * Builds the on-device export bundle and shares it. Layout::
 *
 *     M9_<timestamp>_sweep_NN/
 *       raw_capture.json
 *       diagnostics.json
 *       frames/000001.jpg ...
 *
 * The bundle lives under the app-specific external-files directory so it is
 * retrievable over adb/USB, and is also offered through the Android share sheet.
 * Ground-truth dimensions are never written into it.
 */
object Exporter {

    /** Create a fresh capture-session directory (with its `frames/` subfolder). */
    fun newSessionDir(context: Context, sweepIndex: Int): File {
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val root = File(context.getExternalFilesDir("captures"), "M9_${ts}_sweep_%02d".format(sweepIndex))
        File(root, "frames").mkdirs()
        return root
    }

    fun frameFile(sessionDir: File, frameId: String): File =
        File(File(sessionDir, "frames"), "$frameId.jpg")

    fun writeText(file: File, text: String) {
        file.writeText(text, Charsets.UTF_8)
    }

    /** Zip the whole session directory into `<name>.zip` beside it. */
    fun zip(sessionDir: File): File {
        val zipFile = File(sessionDir.parentFile, "${sessionDir.name}.zip")
        ZipOutputStream(FileOutputStream(zipFile)).use { zos ->
            sessionDir.walkTopDown().filter { it.isFile }.forEach { f ->
                val rel = sessionDir.toURI().relativize(f.toURI()).path
                zos.putNextEntry(ZipEntry("${sessionDir.name}/$rel"))
                f.inputStream().use { it.copyTo(zos) }
                zos.closeEntry()
            }
        }
        return zipFile
    }

    /** A share intent for the zipped bundle via the app's FileProvider. */
    fun shareIntent(context: Context, zipFile: File): Intent {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", zipFile)
        return Intent(Intent.ACTION_SEND).apply {
            type = "application/zip"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }
}
