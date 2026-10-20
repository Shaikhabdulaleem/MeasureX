package com.aymakan.measurex.m9capture

import java.io.File
import java.nio.file.Files
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.junit.Test

/** The pre-ZIP guard: every referenced frame image must exist and be non-empty. */
class ExporterTest {

    private fun sessionDir(): File {
        val dir = Files.createTempDirectory("m9sess").toFile()
        File(dir, "frames").mkdirs()
        return dir
    }

    @Test
    fun allPresentWhenEveryFrameWrittenNonEmpty() {
        val dir = sessionDir()
        for (id in listOf("000001", "000002")) Exporter.frameFile(dir, id).writeBytes(byteArrayOf(1, 2, 3))
        assertTrue(Exporter.allFramesPresent(dir, listOf("000001", "000002")))
    }

    @Test
    fun missingFrameFails() {
        val dir = sessionDir()
        Exporter.frameFile(dir, "000001").writeBytes(byteArrayOf(1))
        assertFalse(Exporter.allFramesPresent(dir, listOf("000001", "000002")))
    }

    @Test
    fun zeroLengthFrameFails() {
        val dir = sessionDir()
        Exporter.frameFile(dir, "000001").writeBytes(byteArrayOf(1))
        Exporter.frameFile(dir, "000002").createNewFile()  // 0 bytes — a half-written image
        assertFalse(Exporter.allFramesPresent(dir, listOf("000001", "000002")))
    }
}
