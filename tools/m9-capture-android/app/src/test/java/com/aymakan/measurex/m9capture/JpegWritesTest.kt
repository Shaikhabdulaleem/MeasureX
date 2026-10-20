package com.aymakan.measurex.m9capture

import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.junit.Test

/** Export gating must never race a pending or failed JPEG write. */
class JpegWritesTest {

    @Test
    fun notReadyWhileAWriteIsPending() {
        val w = JpegWrites()
        w.begin("000001")
        assertEquals(1, w.pending())
        assertFalse(w.exportReady(), "export must wait for the pending write")
        w.succeed("000001")
        assertTrue(w.exportReady())
    }

    @Test
    fun notReadyWhenAReferencedWriteFailed() {
        val w = JpegWrites()
        w.begin("000001"); w.succeed("000001")
        w.begin("000002"); w.fail("000002")
        assertFalse(w.exportReady(), "a failed referenced image blocks export")
        assertEquals(listOf("000002"), w.failed())
    }

    @Test
    fun forgettingAFailedFrameUnblocksExport() {
        val w = JpegWrites()
        w.begin("000001"); w.succeed("000001")
        w.begin("000002"); w.fail("000002")
        assertFalse(w.exportReady())
        w.forget("000002")  // frame dropped from the manifest + controller
        assertTrue(w.exportReady())
    }

    @Test
    fun clearResetsAllState() {
        val w = JpegWrites()
        w.begin("000001")
        w.clear()
        assertEquals(0, w.pending())
        assertTrue(w.exportReady())
    }

    @Test
    fun imageMustMatchIntrinsicsGrid() {
        assertTrue(imageMatchesIntrinsics(640, 480, 640, 480))
        assertFalse(imageMatchesIntrinsics(480, 640, 640, 480))  // rotated grid
        assertFalse(imageMatchesIntrinsics(640, 480, 1280, 960))
    }
}
