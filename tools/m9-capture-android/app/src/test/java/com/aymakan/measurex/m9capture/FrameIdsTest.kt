package com.aymakan.measurex.m9capture

import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.Test

/**
 * Frame ids must be monotonic within a sweep and never reused — a failed JPEG write
 * removes its frame but must not recycle the id onto a later viewpoint.
 */
class FrameIdsTest {

    @Test
    fun allocatesMonotonicZeroPaddedIds() {
        val ids = FrameIds()
        assertEquals("000001", ids.next())
        assertEquals("000002", ids.next())
        assertEquals("000003", ids.next())
    }

    @Test
    fun removalDoesNotReuseAnId() {
        val ids = FrameIds()
        val frames = mutableListOf(ids.next(), ids.next(), ids.next())  // 1,2,3
        // Simulate frame 000002's JPEG write failing → frame dropped from the manifest.
        frames.removeAll { it == "000002" }
        val replacement = ids.next()
        assertEquals("000004", replacement, "a dropped frame must not free its id")
        frames.add(replacement)
        assertEquals(frames.size, frames.toSet().size, "no duplicate ids after a failure")
        assertTrue("000003" in frames && "000002" !in frames)
    }

    @Test
    fun resetStartsANewSweepAtOne() {
        val ids = FrameIds()
        ids.next(); ids.next()
        ids.reset()
        assertEquals("000001", ids.next())
    }
}
