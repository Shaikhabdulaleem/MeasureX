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
        /** Still determining support (ARCore may query the Play Store asynchronously). */
        data object UnknownChecking : State
    }

    /** One synchronous reading of [ArCoreApk.checkAvailability]. */
    fun check(context: Context): State = when (ArCoreApk.getInstance().checkAvailability(context)) {
        ArCoreApk.Availability.SUPPORTED_INSTALLED -> State.SupportedInstalled
        ArCoreApk.Availability.SUPPORTED_NOT_INSTALLED -> State.SupportedNotInstalled
        ArCoreApk.Availability.SUPPORTED_APK_TOO_OLD -> State.SupportedApkTooOld
        ArCoreApk.Availability.UNSUPPORTED_DEVICE_NOT_CAPABLE -> State.UnsupportedDevice
        ArCoreApk.Availability.UNKNOWN_CHECKING,
        ArCoreApk.Availability.UNKNOWN_ERROR,
        ArCoreApk.Availability.UNKNOWN_TIMED_OUT -> State.UnknownChecking
    }

    /** True when metric capture may proceed. */
    fun isReady(state: State): Boolean = state is State.SupportedInstalled

    /** True when the device fundamentally cannot run ARCore (show the blocking message). */
    fun isBlocked(state: State): Boolean = state is State.UnsupportedDevice

    /**
     * Follow the official install/update flow for an installable device. Returns the
     * request status; the caller re-checks availability on resume.
     */
    fun requestInstall(activity: Activity, userRequestedInstall: Boolean): ArCoreApk.InstallStatus =
        ArCoreApk.getInstance().requestInstall(activity, userRequestedInstall)
}
