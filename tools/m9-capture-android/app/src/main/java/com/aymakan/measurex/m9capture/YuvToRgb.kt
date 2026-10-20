package com.aymakan.measurex.m9capture

import android.graphics.Bitmap
import android.media.Image
import java.io.File
import java.io.FileOutputStream

/**
 * Convert an ARCore CPU [Image] (YUV_420_888) to an RGB JPEG, respecting each
 * plane's `rowStride` / `pixelStride` exactly.
 *
 * The saved pixels are in the camera's **native orientation** — no rotation, no
 * mirror, no crop, no resize. The stored width/height and intrinsics therefore
 * describe exactly these pixels, which is what the metric pipeline requires. The
 * on-screen preview may be rotated for the user independently; that never touches
 * the saved image.
 */
object YuvToRgb {

    /** Decode one YUV_420_888 frame into an ARGB_8888 bitmap at native size. */
    fun toBitmap(image: Image): Bitmap {
        require(image.format == android.graphics.ImageFormat.YUV_420_888) {
            "expected YUV_420_888, got ${image.format}"
        }
        val w = image.width
        val h = image.height
        val y = image.planes[0]
        val u = image.planes[1]
        val v = image.planes[2]
        val yBuf = y.buffer
        val uBuf = u.buffer
        val vBuf = v.buffer
        val yRow = y.rowStride
        val uRow = u.rowStride
        val vRow = v.rowStride
        val uPix = u.pixelStride
        val vPix = v.pixelStride

        val argb = IntArray(w * h)
        for (row in 0 until h) {
            val yBase = row * yRow
            val uvRow = row shr 1
            val uBase = uvRow * uRow
            val vBase = uvRow * vRow
            for (col in 0 until w) {
                val yy = (yBuf.get(yBase + col).toInt() and 0xff)
                val uvCol = col shr 1
                val uu = (uBuf.get(uBase + uvCol * uPix).toInt() and 0xff)
                val vv = (vBuf.get(vBase + uvCol * vPix).toInt() and 0xff)
                // BT.601 full-range-ish integer YUV -> RGB.
                val c = yy - 16
                val d = uu - 128
                val e = vv - 128
                val r = clamp((298 * c + 409 * e + 128) shr 8)
                val g = clamp((298 * c - 100 * d - 208 * e + 128) shr 8)
                val b = clamp((298 * c + 516 * d + 128) shr 8)
                argb[row * w + col] = (0xff shl 24) or (r shl 16) or (g shl 8) or b
            }
        }
        return Bitmap.createBitmap(argb, w, h, Bitmap.Config.ARGB_8888)
    }

    /** Write the native-orientation frame as a high-quality JPEG. */
    fun writeJpeg(image: Image, out: File, quality: Int = 95) {
        val bmp = toBitmap(image)
        try {
            FileOutputStream(out).use { fos ->
                bmp.compress(Bitmap.CompressFormat.JPEG, quality, fos)
            }
        } finally {
            bmp.recycle()
        }
    }

    private fun clamp(x: Int): Int = if (x < 0) 0 else if (x > 255) 255 else x
}
