package com.aymakan.measurex.m9capture

import com.aymakan.measurex.m9capture.ArCoreAvailabilityChecker.StartupAction
import com.aymakan.measurex.m9capture.ArCoreAvailabilityChecker.State
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.junit.Test

/** Launch-flow decision for each availability state (Tasks 4 + 8). */
class ArCoreAvailabilityTest {

    @Test
    fun proceedWhenSupportIsKnown() {
        for (s in listOf(State.SupportedInstalled, State.SupportedNotInstalled, State.SupportedApkTooOld)) {
            assertEquals(StartupAction.PROCEED, ArCoreAvailabilityChecker.startupAction(s), "state=$s")
        }
    }

    @Test
    fun recheckWhileStillChecking() {
        // UNKNOWN_CHECKING must poll, not request install as if support were known.
        assertEquals(StartupAction.RECHECK, ArCoreAvailabilityChecker.startupAction(State.UnknownChecking))
    }

    @Test
    fun blockOnUnsupportedOrError() {
        assertEquals(StartupAction.BLOCK, ArCoreAvailabilityChecker.startupAction(State.UnsupportedDevice))
        assertEquals(StartupAction.BLOCK, ArCoreAvailabilityChecker.startupAction(State.CheckError))
        assertTrue(ArCoreAvailabilityChecker.isBlocked(State.CheckError))
        assertTrue(ArCoreAvailabilityChecker.isBlocked(State.UnsupportedDevice))
        assertFalse(ArCoreAvailabilityChecker.isBlocked(State.UnknownChecking))
    }
}
