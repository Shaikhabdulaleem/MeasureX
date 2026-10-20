package com.aymakan.measurex.m9capture

import android.app.Activity
import android.content.Context
import com.google.ar.core.ArCoreApk

/**
 * Runtime ARCore availability. The target device (Samsung A16 4G / SM-A165F) is NOT
 * confirmed on the ARCore certified list, so the app must check at launch and, if AR
 * is unavailable, show a blocking message — never silently fall back to monocular
 * depth or call an RGB-only measurement metric.
 */
object ArCoreAvailabilityChecker {

    sealed interface State {
        /** ARCore is installed and ready — metric capture can run. */
        data object SupportedInstalled : State
        /** Supported, but ARCore must be installed. */
        data object SupportedNotInstalled : State
        /** Supported, but the installed ARCore APK is too old. */
        data object SupportedApkTooOld : State
        /** This device cannot run ARCore — metric pose is impossible here. */
        data object UnsupportedDevice : State
        /** ARCore is still querying support asynchronously — recheck shortly. */
        data object UnknownChecking : State
        /** The availability query errored or timed out — treat as blocked, not "checking". */
        data object CheckError : State
    }

    /** What the launch flow should do next for a given availability [State]. */
    enum class StartupAction {
        /** Support/install is known — continue into the session/install flow. */
        PROCEED,
        /** Support is still being determined — show a message and recheck later. */
        RECHECK,
        /** ARCore cannot run (unsupported, or the check errored/timed out) — block. */
        BLOCK,
    }

    /** One synchronous reading of [ArCoreApk.checkAvailability]. */
    fun check(context: Context): State = when (ArCoreApk.getInstance().checkAvailability(context)) {
        ArCoreApk.Availability.SUPPORTED_INSTALLED -> State.SupportedInstalled
        ArCoreApk.Availability.SUPPORTED_NOT_INSTALLED -> State.SupportedNotInstalled
        ArCoreApk.Availability.SUPPORTED_APK_TOO_OLD -> State.SupportedApkTooOld
        ArCoreApk.Availability.UNSUPPORTED_DEVICE_NOT_CAPABLE -> State.UnsupportedDevice
        ArCoreApk.Availability.UNKNOWN_CHECKING -> State.UnknownChecking
        ArCoreApk.Availability.UNKNOWN_ERROR,
        ArCoreApk.Availability.UNKNOWN_TIMED_OUT -> State.CheckError
    }

    /** True when metric capture may proceed. */
    fun isReady(state: State): Boolean = state is State.SupportedInstalled

    /** True when ARCore cannot run (show the blocking message). */
    fun isBlocked(state: State): Boolean = state is State.UnsupportedDevice || state is State.CheckError

    /**
     * Pure launch decision: proceed into the session/install flow, recheck shortly
     * (support still unknown), or block. A still-"checking" state must not request
     * install as if support were already known; a hard error/timeout blocks cleanly.
     */
    fun startupAction(state: State): StartupAction = when (state) {
        is State.UnsupportedDevice, is State.CheckError -> StartupAction.BLOCK
        is State.UnknownChecking -> StartupAction.RECHECK
        else -> StartupAction.PROCEED
    }

    /**
     * Follow the official install/update flow for an installable device. Returns the
     * request status; the caller re-checks availability on resume.
     */
    fun requestInstall(activity: Activity, userRequestedInstall: Boolean): ArCoreApk.InstallStatus =
        ArCoreApk.getInstance().requestInstall(activity, userRequestedInstall)
}
